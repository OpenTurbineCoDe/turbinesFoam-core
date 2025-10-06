"""This module contains the TurbineModel base class. It contains the default
turbine model parameters and can be superclassed to create custom turbine models.

It also contains methods for reading and writing the turbine model to a YAML file.
This way YAML files are generated based on the default / superclassed turbine model
and can be used as input for the OpenTurbineCode solvers.
"""

import yaml
from pathlib import Path


class TurbineModel:
    def __init__(self, name="DTU10_MW"):

        self.name = name
        self.file_location = Path(__file__).parent.resolve() / "models" / f"{self.name}.yaml"

        # Turbine dimensions
        self.fluid = Fluid()
        self.environment = Environment()
        self.blade = Blade()
        self.rotor = Rotor()
        self.nacelle = Nacelle()
        self.tower = Tower()
        self.hub = Hub()

    def write_to_yaml(self, filename=None):
        """Write the turbine model to a YAML file.

        Args:
            filename (str): The name of the YAML file.
        """
        if filename is None:
            filename = self.file_location

        with open(filename, "w") as file:
            yaml.dump(self.create_dict_for_yaml(), file)

    def create_dict_for_yaml(self):
        """Return the turbine model as a dictionary.

        Returns:
            dict: A dictionary containing the turbine model parameters.
        """
        dict = {
            "fluid": self.fluid.__dict__,
            "environment": self.environment.__dict__,
            "blade": self.blade.__dict__,
            "rotor": self.rotor.__dict__,
            "tower": self.tower.__dict__,
            "hub": self.hub.__dict__,
        }
        return dict

    def read_from_yaml(self, filename=None):
        """Read the turbine model from a YAML file.

        Args:
            filename (str): The name of the YAML file.
        """
        if filename is None:
            filename = self.file_location

        with open(filename, "r") as file:
            data = yaml.safe_load(file)

        self.fluid = Fluid()
        self.environment = Environment()
        self.blade = Blade()
        self.rotor = Rotor()
        self.tower = Tower()
        self.hub = Hub()

        self.fluid.__dict__.update(data["fluid"])
        self.environment.__dict__.update(data["environment"])
        self.blade.__dict__.update(data["blade"])
        self.rotor.__dict__.update(data["rotor"])
        self.tower.__dict__.update(data["tower"])
        self.hub.__dict__.update(data["hub"])

        return self

    def update_model(self, param_dict: dict):
        """
        Update the TurbineModel instance with parameter values.

        Args:
            turbine_model (TurbineModel): Instance of the TurbineModel class.
            param_dict (dict): Dictionary of parameters to update.
                Keys should be in the format '<component>.<attribute>', e.g., 'fluid.velocity'.
        """
        for param, value in param_dict.items():
            component, attribute = param.split(".", 1)
            if hasattr(self, component):
                sub_component = getattr(self, component)
                if hasattr(sub_component, attribute):
                    setattr(sub_component, attribute, value)
                else:
                    raise AttributeError(f"'{component}' does not have an attribute '{attribute}'")
            else:
                raise AttributeError(f"TurbineModel does not have a component '{component}'")


# Default environmental properties
class Environment:
    def __init__(self):
        # Environmental properties
        self.temperature: float = 288.15  # (K) 15 degrees Celsius
        self.speed_of_sound: float = 337.29  # (m/s) Speed of sound at 15 degrees Celsius
        self.atmospheric_pressure: float = 101325  # (Pa) Standard atmospheric pressure
        self.vapor_pressure = 1700  # (Pa) Vapor pressure at 15 degrees Celsius
        self.gravity: float = 9.81  # (m/s^2) Standard gravity

    def read_from_yaml(self, filename):
        with open(filename, "r") as file:
            data = yaml.safe_load(file)

        if "environment" in data:
            self.__dict__.update(data["environment"])

        return self


# Default fluid properties
class Fluid:
    def __init__(self):
        # Free stream properties
        self.velocity = 11.4  # (m/s)
        self.turbulence_intensity = 0.1  # (%)
        self.turbulence_length_scale = 0.1  # (-)

        # Air properties
        self.density = 1.225  # (kg/m^3)
        self.kinematic_viscosity: float = 1.784e-5  # (m^2/s)
        self.dynamic_viscosity = 1.789e-5  # (kg/m/s)
        self.thermal_conductivity = 0.0257  # (W/m/K)
        self.specific_heat = 1006  # (J/kg/K)
        self.thermal_expansion_coefficient = 0.00343  # (1/K)
        self.prandtl_number = 0.71  # (-)
        self.sutherland_constant = 110.4  # (K)
        self.sutherland_temperature = 110.4  # (K)

        # Reference height & Power law exponent
        self.reference_height = 120.0  # (m)
        self.power_law_exponent = 0.1429  # (Open Sea: .1-.15) (Flat Coastal: .12-.20) (Forest/Complex Terrain: .2-.4)

    def read_from_yaml(self, filename):
        with open(filename, "r") as file:
            data = yaml.safe_load(file)

        field = "fluid"

        if field in data:
            self.__dict__.update(data[field])

        return self


# Blade geometry
class Blade:
    def __init__(self):
        # Default blade properties
        self.use_orientations = True
        self.radius = 86.366  # (m)
        self.tip_speed_ratio = 7  # (-)
        self.rotor_speed = 0  # (rpm) Only used if prescribed directly, otherwise calculated from TSR
        self.profiles = ["Cylinder", "FFA_W3_600", "FFA_W3_480", "FFA_W3_360", "FFA_W3_301", "FFA_W3_241"]
        self.blade_profiles = [
            0,
            0,
            1,
            1,
            1,
            2,
            2,
            3,
            3,
            4,
            4,
            4,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
            5,
        ]
        self.pitch_angle = 0  # (degrees)
        self.origins = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        self.orientations = [[0, -4, 0], [120, -4, 0], [240, -4, 0]]
        self.hub_radii = [3, 3, 3]


# Tower geometry
class Tower:
    def __init__(self):
        self.height = 115.6  # (m)
        self.radius = 4.15  # (m)
        self.data = None

    def read_from_yaml(self, filename):
        with open(filename, "r") as file:
            data = yaml.safe_load(file)

        field = "tower"

        if field in data:
            self.__dict__.update(data[field])

        return self


class Nacelle:
    def __init__(self):
        self.yaw = 0  # (degrees)
        self.motion = 0  # Type of motion (0=rigid, 1=sinusoidal, 2=arbitrary)

    def read_from_yaml(self, filename):
        with open(filename, "r") as file:
            data = yaml.safe_load(file)

        field = "nacelle"

        if field in data:
            self.__dict__.update(data[field])

        return self


class Rotor:
    def __init__(self):
        # Default rotor properties
        self.n_blades = 3
        self.tilt_angle = 5  # (degrees)
        self.blade_precone_angle = 2.5  # (degrees)

    def read_from_yaml(self, filename):
        with open(filename, "r") as file:
            data = yaml.safe_load(file)

        field = "rotor"

        if field in data:
            self.__dict__.update(data[field])

        return self


# Hub geometry
class Hub:
    def __init__(self):
        self.radius = 2.8  # (m)
        self.overhang = -7.10  # (m)

    def read_from_yaml(self, filename):
        with open(filename, "r") as file:
            data = yaml.safe_load(file)

        field = "hub"

        if field in data:
            self.__dict__.update(data[field])

        return self


if __name__ == "__main__":
    pass
