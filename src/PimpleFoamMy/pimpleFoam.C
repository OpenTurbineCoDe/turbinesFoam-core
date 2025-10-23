/*---------------------------------------------------------------------------*\

  =========                 |

  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox

   \\    /   O peration     |

    \\  /    A nd           | www.openfoam.com

     \\/     M anipulation  |

-------------------------------------------------------------------------------

  Copyright (C) 2011-2017 OpenFOAM Foundation

  Copyright (C) 2019 OpenCFD Ltd.

-------------------------------------------------------------------------------

License

    This file is part of OpenFOAM.



    OpenFOAM is free software: you can redistribute it and/or modify it

    under the terms of the GNU General Public License as published by

    the Free Software Foundation, either version 3 of the License, or

    (at your option) any later version.



    OpenFOAM is distributed in the hope that it will be useful, but WITHOUT

    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or

    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License

    for more details.



Application

    pimpleFoam.C



Group

    grpIncompressibleSolvers



Description

    Transient solver for incompressible, turbulent flow of Newtonian fluids

    on a moving mesh.

\*---------------------------------------------------------------------------*/

#include <fstream>

#include <string>

#include <cstdlib>

#include <fcntl.h>

#include <unistd.h>

#include <cstdio> // For fdopen, fgets

#include <iostream>



#include "fvCFD.H"

#include "dynamicFvMesh.H"

#include "singlePhaseTransportModel.H"

#include "turbulentTransportModel.H"

#include "pimpleControl.H"

#include "CorrectPhi.H"

#include "fvOptions.H"

#include "localEulerDdtScheme.H"

#include "fvcSmooth.H"



// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //



// --- NEW PERSISTENT FIFO READER/WRITER LOGIC ---



// Cache a single read FD to FOAM_STEP_FIFO

static int openStepFd(const std::string& fifoPath)

{

    static int fd = -1;

    static bool tried = false;

    if (!tried)

    {

        tried = true;

        // O_RDONLY will block until the Core opens the write end, providing a sync point.

        // We use ::open (from <fcntl.h>) instead of std::fstream.

        fd = ::open(fifoPath.c_str(), O_RDONLY);

    }

    return fd;

}



// Blocks on read(stepFd) until a line is available. Returns true on valid message, false on EOF/error.

static bool readStepFd(int fd, Foam::scalar& dt, bool& stop)

{

    stop = false;

    dt = -1.0;

    if (fd < 0) return false;



    // Use a C stream wrapper (FILE*) for line-buffered reading (fgets) on the raw FD.

    // The C++ iostream (std::fstream) method in the original code was the source of the close/block issue.

    FILE* file = fdopen(fd, "r");

    if (!file) { return false; }

   

    char buf[256]; // Buffer for the incoming message line



    // fgets will block until a line is sent by the Core.

    if (std::fgets(buf, sizeof(buf), file) == NULL)

    {

        // EOF or error (writer closed the pipe/link)

        // Note: Do NOT close the FD (fd) or fclose(file) here.

        return false;

    }

   

    std::string line = buf;



    // trim the line

    auto trim = [](std::string& s){

        size_t a = s.find_first_not_of(" \t\r\n");

        size_t b = s.find_last_not_of(" \t\r\n");

        s = (a==std::string::npos) ? std::string() : s.substr(a, b-a+1);

    };

    trim(line);



    if (line == "STOP") { stop = true; return true; }

    if (line == "CONT") { dt = -1.0; return true; }



    try {

        dt = std::stod(line);

        return true;

    } catch (...) {

        // invalid line; ignore and continue

        return false;

    }

}





// Cache a single write FD to FOAM_PERF_FIFO

static int openPerfFd()

{

    static int fd = -1;

    static bool tried = false;

    if (!tried) {

        tried = true;

        if (const char* p = std::getenv("FOAM_PERF_FIFO")) {

            // Blocks until protocol-server opens read end -> good startup sync

            fd = ::open(p, O_WRONLY);

        }

    }

    return fd;

}



static void writePerfJson(double timeValue, double dtValue, long stepIndex)

{

    int fd = openPerfFd();

    if (fd < 0) return;



    // Start with a std::string literal to enable string concatenation (operator+)

    std::string s = std::string("{\"type\":\"STEPPED\"")

                  + ",\"time\":" + std::to_string(timeValue)

                  + ",\"dt\":"    + std::to_string(dtValue)

                  + ",\"step\":"  + std::to_string(stepIndex)

                  + "}";



    // Also addressing the warnings (though they didn't stop the build, good practice)

    if (::write(fd, s.c_str(), s.size()) == -1)

    {

        // Handle error if write failed

    }

    if (::write(fd, "\n", 1) == -1) // Crucial newline

    {

        // Handle error if write failed

    }

}



static void writePerfReady()

{

    int fd = openPerfFd();

    if (fd < 0) return;



    // Send a simple READY signal

    std::string s = "{\"type\":\"READY\"}";



    // Handle return values for robustness

    if (::write(fd, s.c_str(), s.size()) == -1) {}

    if (::write(fd, "\n", 1) == -1) {} // Crucial newline

}

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //



int main(int argc, char *argv[])

{

    argList::addNote

    (

        "Transient solver for incompressible, turbulent flow"

        " of Newtonian fluids on a moving mesh."

    );



    #include "postProcess.H"



    #include "addCheckCaseOptions.H"

    #include "setRootCaseLists.H"

    #include "createTime.H"

    #include "createDynamicFvMesh.H"

    #include "initContinuityErrs.H"

    #include "createDyMControls.H"

    #include "createFields.H"

    #include "createUfIfPresent.H"

    #include "CourantNo.H"

    #include "setInitialDeltaT.H"



    const dictionary& cdict = runTime.controlDict();

    const bool stepMode = cdict.lookupOrDefault<bool>("stepMode", false);



    // Pick FIFO path from controlDict, else env

    word fifoName = cdict.lookupOrDefault<word>("stepFifo", "step.pipe");

    const char* envFifo = std::getenv("FOAM_STEP_FIFO");

    std::string stepFifo = envFifo ? std::string(envFifo) : std::string(fifoName);

    Info<< "External step FIFO: " << stepFifo << nl << endl;

   

    // --- NEW: Open the step FIFO once at startup ---

int stepFd = -1;

    if (stepMode)

    {

        // This open() will block until the Core writes, which is a good startup sync.
        Info << "DEBUG: Attempting to open step FIFO for reading..." << nl;
        stepFd = openStepFd(stepFifo);
        Info << "DEBUG: Step FIFO open returned FD: " << stepFd << nl;

        if (stepFd < 0) {

            Info << "WARNING: Could not open step FIFO. Running in free mode." << nl << endl;

        } else {

            Info<< "Successfully opened step FIFO for continuous read." << nl << endl;

        }



        // ----------------------------------------------------

        // ADD THIS LINE: SIGNAL READY AFTER ALL SETUP IS COMPLETE

        // ----------------------------------------------------

        if (stepFd >= 0 && Pstream::master())

        {
            Info << "Signaling READY on perf.pipe." << nl << endl;
            writePerfReady();
            Info << "Signaled READY on perf.pipe." << nl << endl;

        }

    }



    turbulence->validate();



    if (!LTS)

    {

        #include "CourantNo.H"

        #include "setInitialDeltaT.H"

    }



    // * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //



    Info<< "\nStarting time loop\n" << endl;



    while (runTime.run())

    {

        #include "readDyMControls.H"



        if (stepMode && stepFd >= 0)

        {

            // BLOCK here until something is sent into the FIFO

            Foam::scalar reqDt = -1.0;

            bool stop = false;



            // This read blocks indefinitely, keeping the file descriptor open.

            if (!readStepFd(stepFd, reqDt, stop))

            {

                Info<< "Step FIFO writer closed or error (EOF). Ending run." << nl << endl;

                break;

            }



            if (stop)

            {

                Info<< "Received STOP via FIFO. Ending." << nl << endl;

                break;

            }

            if (reqDt > 0)

            {

                runTime.setDeltaT(reqDt);

                Info<< "Setting deltaT = " << reqDt << nl << endl;

            }

        }

        // else (not stepMode or pipe error): free-run as usual



        ++runTime;



        Info<< "Time = " << runTime.timeName() << nl << endl;



        // --- Pressure-velocity PIMPLE corrector loop

        while (pimple.loop())

        {

            if (pimple.firstIter() || moveMeshOuterCorrectors)

            {

                // Do any mesh changes

                mesh.controlledUpdate();



                if (mesh.changing())

                {

                    MRF.update();



                    if (correctPhi)

                    {

                        // Calculate absolute flux

                        // from the mapped surface velocity

                        phi = mesh.Sf() & Uf();



                        #include "correctPhi.H"



                        // Make the flux relative to the mesh motion

                        fvc::makeRelative(phi, U);

                    }



                    if (checkMeshCourantNo)

                    {

                        #include "meshCourantNo.H"

                    }

                }

            }



            #include "UEqn.H"



            // --- Pressure corrector loop

            while (pimple.correct())

            {

                #include "pEqn.H"

            }



            if (pimple.turbCorr())

            {

                laminarTransport.correct();

                turbulence->correct();

            }

        }



        runTime.write();

        if (Pstream::master())

        {

            // NEW: Signal completion (STEPPED) after time write

            writePerfJson(runTime.value(), runTime.deltaTValue(), runTime.timeIndex());

        }

        runTime.printExecutionTime(Info);

    }



    // Cleanup: Close the step FIFO reader

    if (stepFd >= 0)

    {

        ::close(stepFd);

    }



    Info<< "End\n" << endl;



    return 0;

}



// ************************************************************************* //