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

    You should have received a copy of the GNU General Public License
    along with OpenFOAM.  If not, see <http://www.gnu.org/licenses/>.

Application
    pimpleFoam.C

Group
    grpIncompressibleSolvers

Description
    Transient solver for incompressible, turbulent flow of Newtonian fluids
    on a moving mesh.

    \heading Solver details
    The solver uses the PIMPLE (merged PISO-SIMPLE) algorithm to solve the
    continuity equation:

        \f[
            \div \vec{U} = 0
        \f]

    and momentum equation:

        \f[
            \ddt{\vec{U}} + \div \left( \vec{U} \vec{U} \right) - \div \gvec{R}
          = - \grad p + \vec{S}_U
        \f]

    Where:
    \vartable
        \vec{U} | Velocity
        p       | Pressure
        \vec{R} | Stress tensor
        \vec{S}_U | Momentum source
    \endvartable

    Sub-models include:
    - turbulence modelling, i.e. laminar, RAS or LES
    - run-time selectable MRF and finite volume options, e.g. explicit porosity

    \heading Required fields
    \plaintable
        U       | Velocity [m/s]
        p       | Kinematic pressure, p/rho [m2/s2]
        \<turbulence fields\> | As required by user selection
    \endplaintable

Note
   The motion frequency of this solver can be influenced by the presence
   of "updateControl" and "updateInterval" in the dynamicMeshDict.

\*---------------------------------------------------------------------------*/
#include <fstream>
#include <string>
#include <cstdlib>
#include <fcntl.h>
#include <unistd.h>

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

static bool readStepMessage(const std::string& fifoPath, Foam::scalar& dt, bool& stop)
{
    stop = false;
    dt = -1.0;

    // Block until a writer sends a line
    std::ifstream fifo(fifoPath);
    if (!fifo.is_open()) { return false; }

    std::string line;
    if (!std::getline(fifo, line)) { return false; }

    // trim
    auto trim = [](std::string& s){
        size_t a = s.find_first_not_of(" \t\r\n");
        size_t b = s.find_last_not_of(" \t\r\n");
        s = (a==std::string::npos) ? std::string() : s.substr(a, b-a+1);
    };
    trim(line);

    if (line == "STOP") { stop = true; return true; }
    if (line == "CONT") { dt = -1.0;  return true; }  // keep current Δt

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

    std::string s = "{\"time\":" + std::to_string(timeValue)
                  + ",\"dt\":"    + std::to_string(dtValue)
                  + ",\"step\":"  + std::to_string(stepIndex)
                  + "}";
    ::write(fd, s.c_str(), s.size());
    ::write(fd, "\n", 1);
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

    // Choose FIFO path from env or default ./step.pipe
    const char* envFifo = std::getenv("FOAM_STEP_FIFO");
    std::string stepFifo = envFifo ? std::string(envFifo) : std::string("step.pipe");
    Info<< "External step FIFO: " << stepFifo << nl << endl;
    
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

        // --- External step control (FIFO)
        Foam::scalar reqDt = -1.0;
        bool stop = false;
        if (readStepMessage(stepFifo, reqDt, stop))
        {
            if (stop)
            {
                Info<< "Received STOP. Ending." << nl << endl;
                break;
            }
            if (reqDt > 0)
            {
                runTime.setDeltaT(reqDt);
                Info<< "Setting deltaT = " << reqDt << nl << endl;
            }
        }

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
            writePerfJson(runTime.value(), runTime.deltaTValue(), runTime.timeIndex());
        }
        runTime.printExecutionTime(Info);
    }

    Info<< "End\n" << endl;

    return 0;
}


// ************************************************************************* //
