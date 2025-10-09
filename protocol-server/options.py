import yaml
from turbine_model import TurbineModel
from pathlib import Path
import numpy as np
import pandas as pd


class turbineFoamAxialFlowOptions:
    def __init__(self, model: TurbineModel, run_options):

        # Set turbine model
        self.model = model
        self.block_mesh = BlockMesh(model, run_options)
        self.topo_dict = topoDict(model, run_options)
        self.fv_options = fvOptions(model, run_options)
        self.hex_mesh_dict = HexMeshDict(model, run_options)
        self.control = controlDict(model, run_options)

    def write_to_yaml(self, filename):
        """Write the turbine model to a YAML file.

        Args:
            filename (str): The name of the YAML file.
        """
        save_location = Path(__file__).parent.resolve() / "models" / filename

        with open(save_location, "w") as file:
            yaml.dump(self.create_dict_for_yaml(), file)

    def create_dict_for_yaml(self):
        """Return the turbine model as a dictionary.

        Returns:
            dict: A dictionary containing the turbine model parameters.
        """
        dict = {
            "block_mesh": self.block_mesh.__dict__,
            "topo_dict": self.topo_dict.__dict__,
            "fv_options": self.fv_options.__dict__,
            "hex_mesh_dict": self.hex_mesh_dict.__dict__,
        }
        return dict

    def read_from_yaml(self, filename):
        """Read the turbine model from a YAML file.

        Args:
            filename (str): The name of the YAML file.
        """
        load_location = Path(__file__).parent.resolve() / "models" / filename
        with open(load_location, "r") as file:
            data = yaml.safe_load(file)

        self.block_mesh = BlockMesh(self.model)
        self.topo_dict = topoDict(self.model)
        self.fv_options = fvOptions(self.model)
        self.hex_mesh_dict = HexMeshDict(self.model)

        self.block_mesh.__dict__.update(data["block_mesh"])
        self.topo_dict.__dict__.update(data["topo_dict"])
        self.fv_options.__dict__.update(data["fv_options"])
        self.hex_mesh_dict.__dict__.update(data["hex_mesh_dict"])

        return self


class controlDict:
    def __init__(self, model: TurbineModel, run_options):
        tsr = run_options.tip_speed_ratio
        num_rev = run_options.num_revolutions
        time_step = run_options.time_step
        wind_speed = run_options.wind_speed
        radius = model.blade.radius

        # Calculate end time based on the tip speed ratio and number of revolutions
        omega = tsr * wind_speed / radius  # Angular velocity in rad/s
        one_rev = (2 * np.pi) / omega  # Time for one revolution in seconds
        # self.end_time = num_rev * one_rev  # Total simulation time in seconds
        self.end_time = 1e12  # Run until stopped manually

        # Set the time step based on the number of degrees per time step
        omega_deg = np.degrees(omega)  # Convert to degrees per second
        self.delta_t = 1 / omega_deg * time_step  # Time step for requested degree of rotation


class elementData:
    """
    Hold the element table as a DataFrame and give back a turbinesFoam
    string with an optional twist offset (deg).
    """

    _COLUMNS = ["axial", "radius", "azimuth", "chord", "chordMount", "twist"]

    IEA_15MW_DATA = np.array(
        [
            [0.0, 0.0000000, 0.0, 3.8430000, 0.25, 27.1300],
            [0.0, 5.5400000, 0.0, 3.8430000, 0.25, 27.1300],
            [0.0, 6.8749000, 0.0, 3.8430000, 0.25, 27.1300],
            [0.0, 25.0273000, 0.0, 13.8600000, 0.25, 13.4200],
            [0.0, 28.8948000, 0.0, 12.1863000, 0.25, 11.0000],
            [0.0, 32.7630000, 0.0, 10.8605000, 0.25, 9.1000],
            [0.0, 36.6305000, 0.0, 9.7867000, 0.25, 7.5800],
            [0.0, 40.4980000, 0.0, 8.9012000, 0.25, 6.3300],
            [0.0, 44.3662000, 0.0, 8.1599000, 0.25, 5.2900],
            [0.0, 48.2337000, 0.0, 7.5306000, 0.25, 4.4100],
            [0.0, 52.1012000, 0.0, 6.9902000, 0.25, 3.6500],
            [0.0, 55.9687000, 0.0, 6.5212000, 0.25, 3.0000],
            [0.0, 59.8369000, 0.0, 6.1103000, 0.25, 2.4300],
            [0.0, 63.7044000, 0.0, 5.7477000, 0.25, 1.9300],
            [0.0, 67.5719000, 0.0, 5.4257000, 0.25, 1.4800],
            [0.0, 71.4401000, 0.0, 5.1373000, 0.25, 1.0800],
            [0.0, 75.3076000, 0.0, 4.8783000, 0.25, 0.7200],
            [0.0, 79.1751000, 0.0, 4.6431000, 0.25, 0.4000],
            [0.0, 83.0426000, 0.0, 4.4303000, 0.25, 0.1000],
            [0.0, 86.9108000, 0.0, 4.2357000, 0.25, -0.1700],
            [0.0, 90.7783000, 0.0, 4.0572000, 0.25, -0.4100],
            [0.0, 94.6458000, 0.0, 3.8934000, 0.25, -0.6400],
            [0.0, 98.5140000, 0.0, 3.7422000, 0.25, -0.8500],
            [0.0, 102.3815000, 0.0, 3.6022000, 0.25, -1.0400],
            [0.0, 106.2490000, 0.0, 3.4720000, 0.25, -1.2200],
            [0.0, 110.1165000, 0.0, 3.3516000, 0.25, -1.3900],
            [0.0, 113.9847000, 0.0, 3.2382000, 0.25, -1.5400],
            [0.0, 117.8522000, 0.0, 3.1332000, 0.25, -1.6900],
            [0.0, 121.1310000, 0.0, 0.3486000, 0.25, -1.7700],
        ]
    )

    DTU_10MW_DATA = np.array(
        [
            [0.0, 0.0000, 0.0, 5.3800, 0.25, 14.50],
            [0.0, 2.6430, 0.0, 5.3803, 0.25, 14.50],
            [0.0, 5.3798, 0.0, 5.3800, 0.25, 14.50],
            [0.0, 8.2027, 0.0, 5.4525, 0.25, 14.46],
            [0.0, 11.1030, 0.0, 5.6176, 0.25, 14.23],
            [0.0, 14.0710, 0.0, 5.7204, 0.25, 13.74],
            [0.0, 17.0950, 0.0, 5.7222, 0.25, 12.99],
            [0.0, 20.1640, 0.0, 5.6254, 0.25, 12.15],
            [0.0, 23.2650, 0.0, 5.4757, 0.25, 11.33],
            [0.0, 26.3840, 0.0, 5.3264, 0.25, 10.58],
            [0.0, 29.5080, 0.0, 5.1890, 0.25, 9.93],
            [0.0, 32.6230, 0.0, 5.0415, 0.25, 9.35],
            [0.0, 35.7160, 0.0, 4.8575, 0.25, 8.80],
            [0.0, 38.7730, 0.0, 4.6611, 0.25, 8.26],
            [0.0, 41.7820, 0.0, 4.4552, 0.25, 7.69],
            [0.0, 44.7320, 0.0, 4.2568, 0.25, 7.11],
            [0.0, 47.6110, 0.0, 4.0392, 0.25, 6.54],
            [0.0, 50.4100, 0.0, 3.8328, 0.25, 5.97],
            [0.0, 53.1200, 0.0, 3.6304, 0.25, 5.42],
            [0.0, 55.7340, 0.0, 3.4382, 0.25, 4.90],
            [0.0, 58.2470, 0.0, 3.2537, 0.25, 4.44],
            [0.0, 60.6530, 0.0, 3.0814, 0.25, 4.02],
            [0.0, 62.9500, 0.0, 2.9207, 0.25, 3.63],
            [0.0, 65.1350, 0.0, 2.7688, 0.25, 3.28],
            [0.0, 67.2080, 0.0, 2.6321, 0.25, 2.97],
            [0.0, 69.1670, 0.0, 2.4974, 0.25, 2.68],
            [0.0, 71.0160, 0.0, 2.3905, 0.25, 2.42],
            [0.0, 72.7550, 0.0, 2.2840, 0.25, 2.18],
            [0.0, 74.3860, 0.0, 2.1854, 0.25, 1.95],
            [0.0, 75.9130, 0.0, 2.0958, 0.25, 1.74],
            [0.0, 77.3400, 0.0, 2.0076, 0.25, 1.55],
            [0.0, 78.6710, 0.0, 1.9172, 0.25, 1.36],
            [0.0, 79.9080, 0.0, 1.8231, 0.25, 1.19],
            [0.0, 81.0590, 0.0, 1.7312, 0.25, 1.04],
            [0.0, 82.1250, 0.0, 1.6338, 0.25, 0.90],
            [0.0, 83.1130, 0.0, 1.5275, 0.25, 0.78],
            [0.0, 84.0260, 0.0, 1.4320, 0.25, 0.68],
            [0.0, 84.8700, 0.0, 1.2972, 0.25, 0.58],
            [0.0, 85.6490, 0.0, 1.1633, 0.25, 0.50],
            [0.0, 86.3660, 0.0, 0.6000, 0.25, 0.43],
        ]
    )

    def __init__(self, turbine_model: TurbineModel, run_options) -> None:
        self.twist_offset = run_options.twist_offset
        self.model = turbine_model
        if turbine_model.name == "IEA_15MW_AB_OF":
            self._DATA = self.IEA_15MW_DATA
        elif turbine_model.name == "DTU_10MW_OF":
            self._DATA = self.DTU_10MW_DATA

        self.df = pd.DataFrame(self._DATA, columns=self._COLUMNS)
        if self.twist_offset:
            self.df["twist"] += self.twist_offset  # add or subtract in one go

    # ------------------------------------------------------------------
    def to_foam_string(self) -> str:
        """Return the current DataFrame in turbinesFoam ( ... ) format."""
        s = ""
        for _, r in self.df.iterrows():
            s += (
                f"({r.axial:.1f}    {r.radius:.7f}      {r.azimuth:.1f}     "
                f"{r.chord:.7f}    {r.chordMount:.2f}    {r.twist:.4f})\n"
            )
        return s.rstrip()  # drop final newline if desired


class BlockMesh:
    def __init__(self, model: TurbineModel, run_options: dict):
        diameter = 1.5 * model.blade.radius
        hub_domain = 1.5 * diameter

        default_x_cells = 96
        default_y_cells = 32
        default_z_cells = 24

        cell_scaling_factor = 1

        self.x_cells = int(default_x_cells * cell_scaling_factor)
        self.y_cells = int(default_y_cells * cell_scaling_factor)
        self.z_cells = int(default_z_cells * cell_scaling_factor)

        self.x_downstream = 4 * diameter
        self.x_upstream = -2 * diameter
        self.z_up = hub_domain
        self.z_down = -hub_domain
        self.y_left = -hub_domain
        self.y_right = hub_domain


class topoDict:
    def __init__(self, model: TurbineModel, run_options: dict):
        # Turbine rotor cell set
        self.rotor_radius_of_infl = 1 * (model.hub.radius + model.blade.radius)
        self.rotor_influence_in_x = 1 * model.blade.radius  # Rotor-disc region of influence in x-direction
        self.rotor_start = [-1 * self.rotor_influence_in_x, 0, 0]
        self.rotor_end = [self.rotor_influence_in_x, 0, 0]
        # Tower cell set
        self.tower_radius = model.tower.radius
        self.tower_base = [0, 0, -1 * model.tower.height]
        self.tower_top = [0, 0, 0]
        # Model options
        self.model_tower = run_options.model_tower


class fvOptions:
    def __init__(self, model: TurbineModel, run_options: dict):
        # Header for axialFlowTurbineAlSourceCoeffs
        self.origin = [0, 0, 0]
        self.axis = [
            float(np.cos(np.radians(run_options.tilt_angle))),
            0,
            float(np.sin(np.radians(run_options.tilt_angle))),
        ]
        self.vertical_direction = [0, 0, 1]
        self.free_stream_velocity = [model.fluid.velocity, 0, 0]
        self.tip_speed_ratio = run_options.tip_speed_ratio
        self.rotor_radius = model.blade.radius

        # Blade profile data - Converts profile indices to profile names
        blade_profiles = []
        offset = model.blade.blade_profiles[0]
        for profile in model.blade.blade_profiles:
            blade_profiles.append(f"{model.blade.profiles[profile-offset]}")
        self.blade_profile = blade_profiles

        # Blade information (default for 3 blades at the moment)
        self.num_blades = model.rotor.n_blades
        # self.num_blade_elements = int(2 * (len(self.blade_profile) - 1))
        self.num_blade_elements = 2 * (len(self.blade_profile) - 1)

        # Blade Profile Information
        self.profile_data = list(set(self.blade_profile))  # Gets only unique values

        # Tower information
        self.model_tower = run_options.model_tower
        self.include_tower_drag = False
        self.num_tower_elements = 6
        self.tower_profile = "Cylinder"

        # Default tower properties
        self.include_in_total_drag = False

        # Write element data in the form of (0, radius, height), radius is constant
        element_data = []
        for idx in range(self.num_tower_elements + 1):
            radius = model.tower.radius
            height = -1 * ((self.num_tower_elements - idx) / self.num_tower_elements) * model.tower.height
            element_data.append(f"({"-1"} {height} {radius} )")
        self.tower_element_data = element_data

        # Hub information
        self.model_hub = run_options.model_hub
        self.num_hub_elements = 1
        self.hub_profile = "Cylinder"
        # Axial distance, hub height, diameter
        self.hub_element_data = [
            f"(0 {model.hub.radius} {model.hub.radius})",
            f"(0 {-1 * model.hub.radius} {model.hub.radius})",
        ]

        self.density = model.fluid.density


class HexMeshDict:
    def __init__(self, model: TurbineModel, run_options: dict):
        # Which steps to run
        diameter = model.blade.radius * 2
        self.casellated_mesh = True
        self.snap = True
        self.addLayers = True
        self.turbine_radius = model.blade.radius

        # Geometry definitions for meshing
        self.turbine_type = "searchableCylinder"
        inflow = -1 * self.turbine_radius
        outflow = self.turbine_radius
        self.turbine_point1 = [inflow, 0, 0]
        self.turbine_point2 = [outflow, 0, 0]

        self.tower_type = "searchableCylinder"
        self.tower_point1 = [0, 0, -model.tower.height]  # Tower base to top
        self.tower_point2 = [0, 0, 0]  # Half the tower diameter

        self.turb_zone = "searchableBox"
        margin = 3.0 * model.blade.radius  # or more depending on inflow/outflow
        self.minimum = [-15 * diameter, -margin, -margin]
        self.maximum = [7 * diameter, margin, margin]

        # Castellated Mesh Controls
        self.max_local_cells = 500000
        self.max_global_cells = 10000000
        self.min_refinement_cells = 0
        self.max_load_unbalance = 0.10
        self.n_cells_between_levels = 1  # Number of buffer layers between different levels

        # Explicit feature edge refinement
        # None for now

        # Surface based refinement
        # None for now

        # Region-wise refinement
        # None for now

        # Mesh selection
        # None for now

        # Snap controls
        self.nSmoothPatch = 5  # Number of patch smoothing iterations
        self.tolerance = 2.0  # Maximum distance from surface to snap
        self.nSolveIter = 40  # Number of mesh displacement relaxation iterations
        self.nRelaxIter = 10  # Maximum number of snapping relaxation iterations

        # Feature snapping
        self.nFeatureSnapIter = 10
        self.implicit_feature_snap = True
        self.explicit_feature_snap = True
        self.multi_region_feature_snap = False

        # Layer addition controls
        self.relativeSize = True
        self.expansion_ratio = 1.0
        self.final_layer_thickness = 0.3
        self.min_thickness = 0.25
        self.n_grow = 0

        # Advanced settings
        self.feature_angle = 60
        self.n_relaxation_iterations = 5
        self.n_smooth_surface_normals = 1
        self.n_smooth_thickness = 10
        self.max_face_thickness_ratio = 0.5
        self.max_thickness_to_medial_ratio = 0.3
        self.min_median_axis_angle = 90
        self.n_buffer_cells_no_extrude = 0
        self.n_layer_iteration = 50
        self.n_relaxed_iteration = 20

        # Mesh quality controls
        self.maxNoneOrtho = 70
        self.max_boundary_skewness = 20
        self.max_internal_skewness = 5
        self.max_concave = 80
        self.minVol = 1e-13
        self.min_tet_quality = 1e-30
        self.min_area = -1
        self.min_twist = 0.05
        self.minDeterminant = 0.001
        self.min_face_weight = 0.05
        self.min_volume_ratio = 0.01
        self.min_triangle_twist = -1
        self.n_smooth_scale = 4
        self.error_reduction = 0.75
        self.max_non_orthogonal = 75


if __name__ == "__main__":
    pass
