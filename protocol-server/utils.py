import shutil
from pathlib import Path
from pathing import WSL_ROOT, AXIAL_RUN, FOAM_RUN

TEST_CASE = FOAM_RUN / "test_case"


def make_directory_in_foam_run(directory_name):
    """
    Create a new directory inside the $FOAM_RUN directory using a direct WSL path.

    Parameters:
    directory_name (str): Name of the new directory to create inside the WSL path.
    """
    path_to_case: Path = WSL_ROOT / FOAM_RUN / directory_name
    # Check if directory is already created
    if not path_to_case.exists():
        print(f"Creating new directory: {path_to_case}")
        path_to_case.mkdir(parents=True, exist_ok=True)
    else:
        print(f"Directory already exists: {path_to_case}")

    return None


def allrun_turbinesFoam_case(directory_name):
    """
    Run the turbinesFoam simulation.

    Parameters:
    case_dir (Path): Path to the case directory where the simulation is run.

    Returns:
    bool: True if the simulation completed successfully, False otherwise.
    """
    print("Starting turbinesFoam simulation...")

    case_dir: Path = FOAM_RUN / directory_name

    # Set Allrun permissions for case directory
    permissions_command = f"chmod +x {ubuntu.path_to_ubuntu(case_dir / 'Allrun')}"
    print(f"Ubuntu permissions command: {permissions_command}")
    ubuntu.run_ubuntu_command(permissions_command)

    # Run the Allrun script in the case directory
    command = f"cd {ubuntu.path_to_ubuntu(case_dir)} && ./Allrun"
    print(f"Allrun execute command: {command}")
    ubuntu.run_ubuntu_command(command)


def allclean_turbinesFoam_case(directory_name):
    """
    Clean up the case directory using the Allclean script.

    Parameters:
    case_dir (Path): Directory containing simulation files to be cleaned.
    """
    print("Cleaning case directory...")

    # Run the Allclean script in the case directory
    ubuntu.run_ubuntu_command(f"cd {ubuntu.path_to_ubuntu(directory_name)} && ./Allclean")


def clear_case_directory(directory_name):
    """
    Clear the case directory of all files.

    Parameters:
    case_dir (Path): Path to the case directory containing the simulation files.
    """
    print("Clearing case directory...")

    path_to_case: Path = WSL_ROOT / FOAM_RUN / directory_name

    # Remove the case directory and all its contents
    shutil.rmtree(path_to_case)


def copy_axial_turbine_case(directory_name):
    """
    Copy the axial turbine case files to the output directory.

    Parameters:
    case_dir (Path): Path to the case directory containing the simulation files.
    """
    print("Copying axial turbine case files to new case directory...")

    path_to_case: Path = WSL_ROOT / FOAM_RUN / directory_name

    # We can copy these using windows commands in Powershell
    shutil.copytree(WSL_ROOT / AXIAL_RUN, path_to_case, dirs_exist_ok=True)


def initialize_run(directory_name):
    """Copies the 0.org directory to 0 directory to start the simulation.

    Args:
        directory_name (str): The directory name in $FOAM_RUN to preprocess.
    """
    source = WSL_ROOT / FOAM_RUN / directory_name / "0.org"
    destination = WSL_ROOT / FOAM_RUN / directory_name / "0"

    # Copy the 0.org directory to 0 directory
    shutil.copytree(source, destination, dirs_exist_ok=True)

    return None


def create_paraview_file(directory_name):
    """
    Create a Paraview file for the case directory.

    Parameters:
    directory_name (str): Name of the directory where the Paraview file will be created.
    """
    path_to_case: Path = FOAM_RUN / directory_name

    ubuntu.run_ubuntu_command(f"cd {ubuntu.path_to_ubuntu(path_to_case)} && touch case.foam")


if __name__ == "__main__":
    # Create a new directory in the $FOAM_RUN directory
    make_directory_in_foam_run("test_case")

    # Clear the case directory
    clear_case_directory("test_case")

    # Copy the axial turbine case files to the output directory
    copy_axial_turbine_case("test_case")

    # Preprocess the case directory
    initialize_run("test_case")

    # Run the turbinesFoam simulation
    allrun_turbinesFoam_case("test_case")

    # Extract the simulation results
