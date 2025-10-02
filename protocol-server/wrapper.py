from pathlib import Path
import utils as util
from turbine_model import TurbineModel
from file_generator import FileGenerator
from options import turbineFoamAxialFlowOptions
import post_processing as pp

BOOL_RUN_CASE = True
BOOL_POST_PROCESS = True

GEN_FILES = True

MODEL = "IEA_15MW_AB_OF"  # Example turbine model, can be replaced with any valid model name
# MODEL = "DTU_10MW_OF"


class turbinesFoamWrapper:
    def __init__(self, turbine: TurbineModel, run_options):
        self.turbine: TurbineModel = turbine
        self.run_options = run_options
        self.case_name = run_options.case_name
        self.case_class = run_options.case_class

        self.case_dir = Path(util.WSL_ROOT / util.FOAM_RUN / self.case_name)

        # Load the case options
        self.foam_options = self.load_case(self.turbine, self.case_class, run_options)

    def load_case(self, turbine: TurbineModel, case_name: str, run_options: dict):
        """Load a case from the OpenTurbineCode turbine model.

        Args:
            turbine (TurbineModel): The turbine model to load.
            case_name (str): The name of the case to load.
        """
        if case_name == "axialFlowTurbineAL":
            options = turbineFoamAxialFlowOptions(turbine, run_options)
        else:
            raise ValueError(f"Case {case_name} is not supported.")

        return options

    def main(self):
        if BOOL_RUN_CASE:
            # Manage the case files
            self.manage_case_files()

            # Preprocess the case
            self.preprocess()

            # Run the simulation
            self.run_simulation()

        # Post-process the simulation
        if BOOL_POST_PROCESS:
            self.post_process()

    def manage_case_files(self):
        # Create a new directory in the $FOAM_RUN directory
        util.make_directory_in_foam_run(self.case_name)

        # Clear the case directory
        util.clear_case_directory(self.case_name)

        # Copy the axial turbine case files to the output directory
        util.copy_axial_turbine_case(self.case_name)

    def preprocess(self):
        """Preprocess the case directory by generating the OpenFOAM files.
        """
        print("Preprocessing case files...")
        if GEN_FILES:
            generator = FileGenerator(self.turbine, self.run_options)

            # Generate the OpenFOAM files to the case directory
            generator.generate_files(self.case_dir)
        pass

    def run_simulation(self):
        # Preprocess the case directory
        util.initialize_run(self.case_name)

        # Run the turbinesFoam simulation
        util.allrun_turbinesFoam_case(self.case_name)

    def post_process(self):
        # Extract the simulation results
        print("Post-processing simulation results...")
        util.create_paraview_file(self.case_name)

        match self.case_class:
            case "axialFlowTurbineAL":
                post = pp.AxialFlowPostProcessing(self.case_name, self.turbine)
                post.plot_cp()
                post.plot_spanwise()
                post.calc_performance()
            case _:
                print("Invalid case class.")


# Example usage
if __name__ == "__main__":
    turbine = TurbineModel(name=MODEL)
    turbine.read_from_yaml()
    for tsr in range(12, 13):
        class RunOptions:
            def __init__(self):
                self.case_name = "test_case"
                self.case_class = "axialFlowTurbineAL"
                self.num_revolutions = 1
                self.time_step = 5  # degrees per time step
                self.model_tower = False
                self.model_hub = False
                self.tip_speed_ratio = tsr
                self.wind_speed = 12.8  # m/s
                self.twist_offset = 0.0
                self.tilt_angle = -6.0  # degrees

        wrapper = turbinesFoamWrapper(turbine, run_options=RunOptions())
        wrapper.main()
