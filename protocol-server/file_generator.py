"""This module contains functions to generate axialFlowTurbine files for turbinesFoam."""

from pathlib import Path
from turbine_model import TurbineModel
from options import BlockMesh, topoDict, fvOptions, HexMeshDict, elementData, controlDict

from typing import List


class FileGenerator:
    def __init__(self, turbine: TurbineModel, run_options):
        self.turbine = turbine
        self.block_mesh = BlockMesh(turbine, run_options)
        self.topo = topoDict(turbine, run_options)
        self.fv_options = fvOptions(turbine, run_options)
        self.snappy = HexMeshDict(turbine, run_options)
        self.element_data = elementData(turbine, run_options)
        self.control = controlDict(turbine, run_options)

    def generate_files(self, file_path: Path):
        """Generate all necessary files for the axialFlowTurbine case."""
        self.generate_elementData(file_path)
        self.generate_blockMeshDict(file_path)
        self.generate_topoSetDict(file_path)
        self.generate_fvOptions(file_path)
        self.generate_snappyHexMeshDict(file_path)
        self.generate_controlDict(file_path)

    def generate_controlDict(self, file_path: Path):
        contents = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  6                                     |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     pimpleFoamMy;

startFrom       startTime;

startTime       0;

stopAt          endTime;

endTime         {self.control.end_time};

deltaT          {self.control.delta_t};

writeControl    runTime;

writeInterval   2;

writeFormat     binary;

writePrecision  12;

writeCompression uncompressed;

timeFormat      general;

timePrecision   6;

runTimeModifiable true;

adjustTimeStep  false;

maxCo           0.9;

stepMode        true;

stepFifo       step.pipe;

libs
(
    "libturbinesFoam.so"
);


// ************************************************************************* //"""

        # Write the controlDict file
        with open(file_path / "system" / "controlDict", "w") as file:
            file.write(contents)

        return None

    def generate_elementData(self, file_path: Path):
        """Generate the elementData file for the axialFlowTurbine case.

        Args:
            turbine (AxialTurbine): AxialTurbine object.

        Returns:
            str: elementData file contents.
        """
        # Define the elementData file contents
        contents = """// Blade element data
// axialDistance, radius, azimuth, chord, chordMount, twist\n"""
        contents = contents + self.element_data.to_foam_string()

        with open(file_path / "system" / "elementData", "w") as file:
            file.write(contents)

        return None

    def generate_blockMeshDict(self, file_path: Path):
        """Generate the blockMeshDict file for the axialFlowTurbine case.

        Args:
            turbine (AxialTurbine): AxialTurbine object.

        Returns:
            str: blockMeshDict file contents.
        """

        # Define the blockMeshDict file contents
        contents = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\   /   O peration     | Version:  3.0.x                                 |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

convertToMeters 1;

// Control volume vertices
vertices
(
    ( {self.block_mesh.x_downstream}  {self.block_mesh.y_left}  {self.block_mesh.z_down} )   // 0
    ( {self.block_mesh.x_downstream}  {self.block_mesh.y_right}  {self.block_mesh.z_down} )  // 1
    ( {self.block_mesh.x_upstream}  {self.block_mesh.y_right}  {self.block_mesh.z_down} )  // 2
    ( {self.block_mesh.x_upstream}  {self.block_mesh.y_left}  {self.block_mesh.z_down} )  // 3
    ( {self.block_mesh.x_downstream}  {self.block_mesh.y_left}  {self.block_mesh.z_up} )  // 4
    ( {self.block_mesh.x_downstream}  {self.block_mesh.y_right}  {self.block_mesh.z_up} )  // 5
    ( {self.block_mesh.x_upstream}  {self.block_mesh.y_right}  {self.block_mesh.z_up} )  // 6
    ( {self.block_mesh.x_upstream}  {self.block_mesh.y_left}  {self.block_mesh.z_up} )  // 7
);

// Control volume blocks
blocks
(
    hex (0 1 2 3 4 5 6 7)
    ({self.block_mesh.y_cells} {self.block_mesh.x_cells} {self.block_mesh.z_cells})
    simpleGrading (1 1 1)
);

// Control volume surface patches
boundary
(
    inlet
    {{
    type patch;
    faces
        (
            (2 6 7 3)
        );
    }}

    outlet
    {{
    type patch;
    faces
        (
            (0 4 5 1)
        );
    }}

    walls
    {{
    type wall;
    faces
        (
            (1 5 6 2)
            (4 0 3 7)
        );
    }}

    top
    {{
    type wall;
    faces
        (
            (4 7 6 5)
        );
    }}

    bottom
    {{
    type wall;
    faces
        (
            (0 1 2 3)
        );
    }}
);

edges
(
);

mergePatchPairs
(
);

// ************************************************************************* //
"""

        # Write the blockMeshDict file
        with open(file_path / "system" / "blockMeshDict", "w") as file:
            file.write(contents)

        return None

    def generate_topoSetDict(self, file_path: Path):
        """Generate the topoSetDict file for the axialFlowTurbine case.

        Args:
            turbine (AxialTurbine): AxialTurbine object.

        Returns:
            str: topoSetDict file contents.
        """

        contents = f"""/*--------------------------------*- C++ -*----------------------------------*\\
    | =========                 |                                                 |
    | \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
    |  \\    /   O peration     | Version:  3.0.x                                 |
    |   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
    |    \\/     M anipulation  |                                                 |
    \\*---------------------------------------------------------------------------*/
    FoamFile
    {{
        version     2.0;
        format      ascii;
        class       dictionary;
        object      topoSetDict;
    }}

    // * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

    actions
    (
        // Turbine rotor cell set
        {{
            name 	turbine;
            type	cellSet;
            action	new;
            source	cylinderToCell;
            sourceInfo
            {{
                type    cylinder;
                // Starting at the blade root along Z-axis and ending at the rotor apex
                p1      ({self.topo.rotor_start[0]} {self.topo.rotor_start[1]} {-1 * self.topo.rotor_start[2]});
                p2      ({self.topo.rotor_end[0]} {self.topo.rotor_end[1]} {self.topo.rotor_end[2]});
                radius  {self.topo.rotor_radius_of_infl};
            }}
        }}
"""
        if self.topo.model_tower:
            contents += f"""
            // Tower cell set
            {{
                name 	turbine;
                type	cellSet;
                action	add;
                source	cylinderToCell;
                sourceInfo
                {{
                    // Starting and ending tower points
                    type    cylinder;
                    p1      ({self.topo.tower_base[0]} {self.topo.tower_base[1]} {self.topo.tower_base[2]});
                    p2      ({self.topo.tower_top[0]} {self.topo.tower_top[1]} {self.topo.tower_top[2]});
                    radius  {self.topo.tower_radius};          // Approximate tower radius
                }}
            }}
"""
        contents += f"""
        // Convert cellSet to cellZone for fvOptions
        {{
            name    turbine;
            type    cellZoneSet;
            action  new;
            source  setToCellZone;
            sourceInfo
            {{
                set turbine;
            }}
        }}
    );


    // ************************************************************************* //
    """
        with open(file_path / "system" / "topoSetDict", "w") as file:
            file.write(contents)

        return None

    def generate_fvOptions(self, file_path: Path):
        """Generate the fvOptions file for the axialFlowTurbine case using the fvOptions object."""

        def write_header():
            return """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  6                                     |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvOptions;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

    """

        def write_turbine_base():
            return f"""turbine
{{
    type            axialFlowTurbineALSource;
    active          on;

    axialFlowTurbineALSourceCoeffs
    {{
        fieldNames          (U);
        selectionMode       cellSet;
        cellSet             turbine;
        origin              {str(tuple(self.fv_options.origin)).replace(",", "")};
        axis                {str(tuple(self.fv_options.axis)).replace(",", "")};
        verticalDirection   {str(tuple(self.fv_options.vertical_direction)).replace(",", "")};
        freeStreamVelocity  {str(tuple(self.fv_options.free_stream_velocity)).replace(",", "")};
        tipSpeedRatio       {self.fv_options.tip_speed_ratio};
        rotorRadius         {self.fv_options.rotor_radius};
        density             {self.fv_options.density};

        dynamicStall
        {{
            active          off;
            dynamicStallModel LeishmanBeddoes;
        }}

        endEffects
        {{
            active          off;
            endEffectsModel Glauert; // Glauert || Shen || liftingLine
            GlauertCoeffs
            {{
                tipEffects  on;
                rootEffects on;
            }}
            ShenCoeffs
            {{
                c1          0.125;
                c2          21;
                tipEffects  on;
                rootEffects on;
            }}
        }}

    """

        def write_blades():
            azimuthal_offset = 90
            blade_str = "    blades\n        {\n"
            for idx in range(1, self.fv_options.num_blades + 1):
                blade_str += f"""            blade{idx}
            {{
                writePerf           true;
                writeElementPerf    true;
                nElements           {self.fv_options.num_blade_elements};
                elementProfiles
                (
    """
                for profile in self.fv_options.blade_profile:
                    blade_str += f"                    {profile}\n"
                blade_str += "                );\n"
                # Azimuthal offset for additional blade
                if idx > 1:
                    blade_str += f"                azimuthalOffset {(idx - 1) * 120.0 + azimuthal_offset};\n"
                # Always write reference to elementData file
                blade_str += """                elementData
                (
                    #include "elementData"
                );\n"""
                blade_str += "            }\n"
            blade_str += "        }\n"
            return blade_str

        def write_tower():
            return (
                f"""        tower
            {{
                includeInTotalDrag  {"true" if self.fv_options.include_tower_drag else "false"};
                nElements   {self.fv_options.num_tower_elements};
                elementProfiles ({self.fv_options.tower_profile});
                elementData
                (
    """
                + "\n".join([f"                {data}" for data in self.fv_options.tower_element_data])
                + "\n            );\n        }\n"
            )

        def write_hub():
            return (
                f"""        hub
            {{
                nElements   {self.fv_options.num_hub_elements};
                elementProfiles ({self.fv_options.hub_profile});
                elementData
                (
    """
                + "\n".join([f"                {data}" for data in self.fv_options.hub_element_data])
                + "\n            );\n        }\n"
            )

        def write_profile_data():
            profile_str = "        profileData\n        {\n"
            for profile_name in self.fv_options.profile_data:
                profile_str += f"""            {profile_name}
                {{
                    data (#include "../../resources/foilData/{profile_name}");
                }}\n"""
            profile_str += "        }\n"
            return profile_str

        # Combine all sections to form the full contents of the fvOptions file
        contents = (
            write_header()
            + write_turbine_base()
            + write_blades()
            + (write_tower() if self.fv_options.model_tower else "")
            + (write_hub() if self.fv_options.model_hub else "")
            + write_profile_data()
            + "    }\n}\n\n// ************************************************************************* //\n"
        )

        # Write the contents to the fvOptions file
        with open(file_path / "system" / "fvOptions", "w") as file:
            file.write(contents)

        return None

    # ===================================================================
    # ==                   SNAPPY HEX HELPERS                          ==
    # ===================================================================

    def _format_coordinates(self, coords: List[float]) -> str:
        """Helper to format a list of coordinates into OpenFOAM format."""
        return f"({coords[0]:.2f} {coords[1]:.2f} {coords[2]:.2f})"

    def _generate_geometry_section(self, geometry_objects: List) -> str:
        """Generates the geometry dictionary content."""
        geo_content = ""
        for obj in geometry_objects:
            # Handle specific properties for boxes vs. cylinders
            if obj.type == "searchableCylinder":
                props = (
                    f"            point1 {self._format_coordinates(obj.start)};\n"
                    f"            point2 {self._format_coordinates(obj.end)};\n"
                    f"            radius {obj.radius:.2f};\n"
                )
            elif obj.type == "searchableBox":
                props = (
                    f"            min {self._format_coordinates(obj.min)};\n"
                    f"            max {self._format_coordinates(obj.max)};\n"
                )
            else:
                continue  # Skip unknown types

            geo_content += (
                f"        {obj.name}\n" f"        {{\n" f"            type {obj.type};\n" f"{props}" f"        }}\n\n"
            )
        return geo_content.strip()

    def _generate_refinement_section(self, refinement_regions: List) -> str:
        """Generates the refinementRegions dictionary content."""
        refine_content = ""
        for region in refinement_regions:
            # Format the levels list: [(dist, level), ...]
            levels_str = "\n".join(f"                    ({dist:.4f} {level})" for dist, level in region.levels)

            # Distance mode requires nested levels, inside mode uses one line
            level_block = f"                levels (\n{levels_str}\n                );"

            # Handle optional distanceMode
            distance_mode_line = ""
            if region.distance_mode:
                distance_mode_line = f"            distanceMode {region.distance_mode};\n"

            refine_content += (
                f"        {region.name}\n"
                f"        {{\n"
                f"            mode {region.mode};\n"
                f"{distance_mode_line}"
                f"{level_block}\n"
                f"        }}\n"
            )
        return refine_content.strip()

    # ===================================================================
    # ==                  SNAPPY HEX FILE GENERATOR                    ==
    # ===================================================================

    def generate_snappyHexMeshDict(self, file_path: Path):
        """Generates the snappyHexMeshDict file for the axialFlowTurbine case."""
        # Load the template and fill in dynamic sections

        # 1. Generate the geometry content dynamically
        geometry_content = self._generate_geometry_section(self.snappy.geometry_objects)

        # 2. Generate the refinement regions content dynamically
        refinement_content = self._generate_refinement_section(self.snappy.refinement_regions)

        contents = f"""/*--------------------------------*- C++ -*----------------------------------*\\
    | =========                 |                                                 |
    | \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
    |  \\    /   O peration     | Version:  3.0.x                                 |
    |   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
    |    \\/     M anipulation  |                                                 |
    \\*---------------------------------------------------------------------------*/
    FoamFile
    {{
        version     2.0;
        format      ascii;
        class       dictionary;
        object      snappyHexMeshDict;
    }}

    // * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

    // Which of the steps to run
    castellatedMesh true;
    snap            true;
    addLayers       false;


    // Geometry. Definition of all surfaces. All surfaces are of class
    // searchableSurface.
    // Surfaces are used
    // - to specify refinement for any mesh cell intersecting it
    // - to specify refinement for any mesh cell inside/outside/near
    // - to 'snap' the mesh boundary to the surface
    geometry
    {{
{geometry_content}
    }};


    // Settings for the castellatedMesh generation.
    castellatedMeshControls
    {{

        // Refinement parameters
        // ~~~~~~~~~~~~~~~~~~~~~

        // If local number of cells is >= maxLocalCells on any processor
        // switches from from refinement followed by balancing
        // (current method) to (weighted) balancing before refinement.
        maxLocalCells {self.snappy.max_local_cells};    // Increase local cell count to handle refinement within each region

        // Overall cell limit (approximately). Refinement will stop immediately
        // upon reaching this number so a refinement level might not complete.
        // Note that this is the number of cells before removing the part which
        // is not 'visible' from the keepPoint. The final number of cells might
        // actually be a lot less.
        maxGlobalCells {self.snappy.max_global_cells}; // Increase global cell count to accommodate the larger geometry

        // The surface refinement loop might spend lots of iterations
        // refining just a few cells. This setting will cause refinement
        // to stop if <= minimumRefine are selected for refinement. Note:
        // it will at least do one iteration (unless the number of cells
        // to refine is 0)
        minRefinementCells {self.snappy.min_refinement_cells};

        // Allow a certain level of imbalance during refining
        // (since balancing is quite expensive)
        // Expressed as fraction of perfect balance (= overall number of cells /
        // nProcs). 0=balance always.
        maxLoadUnbalance {self.snappy.max_load_unbalance};


        // Number of buffer layers between different levels.
        // 1 means normal 2:1 refinement restriction, larger means slower
        // refinement.
        nCellsBetweenLevels {self.snappy.n_cells_between_levels};



        // Explicit feature edge refinement
        // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        // Specifies a level for any cell intersected by its edges.
        // This is a featureEdgeMesh, read from constant/triSurface for now.
        features
        (
            //{{
            //    file "someLine.eMesh";
            //    level 2;
            //}}
        );



        // Surface based refinement
        // ~~~~~~~~~~~~~~~~~~~~~~~~

        // Specifies two levels for every surface. The first is the minimum level,
        // every cell intersecting a surface gets refined up to the minimum level.
        // The second level is the maximum level. Cells that 'see' multiple
        // intersections where the intersections make an
        // angle > resolveFeatureAngle get refined up to the maximum level.

        refinementSurfaces
        {{
        }}


        resolveFeatureAngle 30;


        // Region-wise refinement
        // ~~~~~~~~~~~~~~~~~~~~~~

        // Specifies refinement level for cells in relation to a surface. One of
        // three modes
        // - distance. 'levels' specifies per distance to the surface the
        //   wanted refinement level. The distances need to be specified in
        //   descending order.
        // - inside. 'levels' is only one entry and only the level is used. All
        //   cells inside the surface get refined up to the level. The surface
        //   needs to be closed for this to be possible.
        // - outside. Same but cells outside.

        refinementRegions
        {{
{refinement_content}
        }}


        // Mesh selection
        // ~~~~~~~~~~~~~~

        // After refinement patches get added for all refinementSurfaces and
        // all cells intersecting the surfaces get put into these patches. The
        // section reachable from the locationInMesh is kept.
        // NOTE: This point should never be on a face, always inside a cell, even
        // after refinement.
        locationInMesh (0.3124 0 0);

        // Whether any faceZones (as specified in the refinementSurfaces)
        // are only on the boundary of corresponding cellZones or also allow
        // free-standing zone faces. Not used if there are no faceZones.
        allowFreeStandingZoneFaces true;

        // Optional: do not remove cells likely to give snapping problems
        handleSnapProblems false;

        // Optional: switch off topological test for cells to-be-squashed
        //           and use geometric test instead
        useTopologicalSnapDetection false;
    }}



    // Settings for the snapping.
    snapControls
    {{
        // Number of patch smoothing iterations before finding correspondence
        // to surface
        nSmoothPatch 5;

        // Maximum relative distance for points to be attracted by surface.
        // True distance is this factor times local maximum edge length.
        // Note: changed(corrected) w.r.t 17x! (17x used 2* tolerance)
        tolerance 2.0;

        // Number of mesh displacement relaxation iterations.
        nSolveIter {self.snappy.nSolveIter};

        // Maximum number of snapping relaxation iterations. Should stop
        // before upon reaching a correct mesh.
        nRelaxIter {self.snappy.nRelaxIter};

        // Feature snapping

            // Number of feature edge snapping iterations.
            // Leave out altogether to disable.
            nFeatureSnapIter 10;

            // Detect (geometric only) features by sampling the surface
            // (default=false).
            implicitFeatureSnap true;

            // Use castellatedMeshControls::features (default = true)
            explicitFeatureSnap true;

            // Detect features between multiple surfaces
            // (only for explicitFeatureSnap, default = false)
            multiRegionFeatureSnap false;


        // wip: disable snapping to opposite near surfaces (revert to 22x behaviour)
        detectNearSurfacesSnap false;
    }}



    // Settings for the layer addition.
    addLayersControls
    {{
        // Are the thickness parameters below relative to the undistorted
        // size of the refined cell outside layer (true) or absolute sizes (false).
        relativeSizes true;

        // Per final patch (so not geometry!) the layer information
        layers
        {{
        }}

        // Expansion factor for layer mesh
        expansionRatio 1.0;


        // Wanted thickness of final added cell layer. If multiple layers
        // is the thickness of the layer furthest away from the wall.
        // See relativeSizes parameter.
        finalLayerThickness 0.3;

        // Minimum thickness of cell layer. If for any reason layer
        // cannot be above minThickness do not add layer.
        // See relativeSizes parameter.
        minThickness 0.25;

        // If points get not extruded do nGrow layers of connected faces that are
        // also not grown. This helps convergence of the layer addition process
        // close to features.
        // Note: changed(corrected) w.r.t 17x! (didn't do anything in 17x)
        nGrow 0;


        // Advanced settings

        // When not to extrude surface. 0 is flat surface, 90 is when two faces
        // are perpendicular
        featureAngle 60;

        // Maximum number of snapping relaxation iterations. Should stop
        // before upon reaching a correct mesh.
        nRelaxIter 5;

        // Number of smoothing iterations of surface normals
        nSmoothSurfaceNormals 1;

        // Number of smoothing iterations of interior mesh movement direction
        nSmoothNormals 3;

        // Smooth layer thickness over surface patches
        nSmoothThickness 10;

        // Stop layer growth on highly warped cells
        maxFaceThicknessRatio 0.5;

        // Reduce layer growth where ratio thickness to medial
        // distance is large
        maxThicknessToMedialRatio 0.3;

        // Angle used to pick up medial axis points
        // Note: changed(corrected) w.r.t 16x! 90 degrees corresponds to 130 in 16x.
        minMedianAxisAngle 90;

        // Create buffer region for new layer terminations
        nBufferCellsNoExtrude 0;


        // Overall max number of layer addition iterations. The mesher will exit
        // if it reaches this number of iterations; possibly with an illegal
        // mesh.
        nLayerIter 50;

        // Max number of iterations after which relaxed meshQuality controls
        // get used. Up to nRelaxIter it uses the settings in meshQualityControls,
        // after nRelaxIter it uses the values in meshQualityControls::relaxed.
        nRelaxedIter 20;
    }}



    // Generic mesh quality settings. At any undoable phase these determine
    // where to undo.
    meshQualityControls
    {{
        //- Maximum non-orthogonality allowed. Set to 180 to disable.
        maxNonOrtho 70;

        //- Max skewness allowed. Set to <0 to disable.
        maxBoundarySkewness 20;
        maxInternalSkewness 5;

        //- Max concaveness allowed. Is angle (in degrees) below which concavity
        //  is allowed. 0 is straight face, <0 would be convex face.
        //  Set to 180 to disable.
        maxConcave {self.snappy.max_concave};

        //- Minimum pyramid volume. Is absolute volume of cell pyramid.
        //  Set to a sensible fraction of the smallest cell volume expected.
        //  Set to very negative number (e.g. -1E30) to disable.
        minVol 1e-13;

        //- Minimum quality of the tet formed by the face-centre
        //  and variable base point minimum decomposition triangles and
        //  the cell centre.  Set to very negative number (e.g. -1E30) to
        //  disable.
        //     <0 = inside out tet,
        //      0 = flat tet
        //      1 = regular tet
        minTetQuality 1e-30;

        //- Minimum face area. Set to <0 to disable.
        minArea -1;

        //- Minimum face twist. Set to <-1 to disable. dot product of face normal
        //- and face centre triangles normal
        minTwist 0.05;

        //- minimum normalised cell determinant
        //- 1 = hex, <= 0 = folded or flattened illegal cell
        minDeterminant 0.001;

        //- minFaceWeight (0 -> 0.5)
        minFaceWeight 0.05;

        //- minVolRatio (0 -> 1)
        minVolRatio 0.01;

        //must be >0 for Fluent compatibility
        minTriangleTwist -1;

        //- if >0 : preserve single cells with all points on the surface if the
        //  resulting volume after snapping (by approximation) is larger than
        //  minVolCollapseRatio times old volume (i.e. not collapsed to flat cell).
        //  If <0 : delete always.
        //minVolCollapseRatio 0.5;


        // Advanced

        //- Number of error distribution iterations
        nSmoothScale 4;
        //- amount to scale back displacement at error points
        errorReduction 0.75;



        // Optional : some meshing phases allow usage of relaxed rules.
        // See e.g. addLayersControls::nRelaxedIter.
        relaxed
        {{
            //- Maximum non-orthogonality allowed. Set to 180 to disable.
            maxNonOrtho 75;
        }}
    }}


    // Advanced

    // Flags for optional output
    // 0 : only write final meshes
    // 1 : write intermediate meshes
    // 2 : write volScalarField with cellLevel for postprocessing
    // 4 : write current intersections as .obj files
    debug 0;


    // Merge tolerance. Is fraction of overall bounding box of initial mesh.
    // Note: the write tolerance needs to be higher than this.
    mergeTolerance 1e-6;


    // ************************************************************************* //
    """

        with open(file_path / "system" / "snappyHexMeshDict", "w") as file:
            file.write(contents)

        return None


if __name__ == "__main__":
    pass
    # case_dir = WSL_ROOT / FOAM_RUN / "test_case"
    # model = TurbineModel()
    # generator = FileGenerator(model)
    # generator.generate_files(case_dir)
