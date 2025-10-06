from __future__ import division, print_function, absolute_import
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt
from pathing import FOAM_RUN
from turbine_model import TurbineModel


class ElementData:
    def __init__(self, element_number, df):
        self.element_number = element_number
        self.df = df

        self.root_dist = float(self.df.root_dist.iloc[-1])
        self.urel = float(self.df.rel_vel_mag.iloc[-1])
        self.alpha_deg = float(self.df.alpha_deg.iloc[-1])
        self.cl = float(self.df.cl.iloc[-1])
        self.f = float(self.df.end_effect_factor.iloc[-1])


class AxialFlowPostProcessing:
    def __init__(self, case_name, turbine_model: TurbineModel = None):
        self.case_dir: Path = FOAM_RUN / case_name

        # Extract the simulation results
        self.turbine_df: pd.DataFrame = self.extract_turbine_data()
        self.turbine_model: TurbineModel = turbine_model

        # Extract the spanwise results, this is a dictionary of DataFrames
        self.spanwise_dict = self.extract_spanwise_data()

    def extract_turbine_data(self):
        """Extracts the turbine data from the simulation results.

        Returns:
            DataFrame: Pandas DataFrame containing the turbine data.
        """
        turbine_results_dir = self.case_dir / "postProcessing" / "turbines" / "0"
        turbine_df = pd.read_csv(turbine_results_dir / 'turbine.csv')

        return turbine_df

    def calc_performance(self, angle0=3600.0):
        """Calculate the performance of the turbine based on the simulation results."""
        df = self.turbine_df.copy().drop_duplicates("time", keep="last")
        df = df[df["angle_deg"] >= angle0]

        # Calculate mean values
        mean_tsr = df.tsr.mean()
        mean_cp = df.cp.mean()
        mean_cq = df.ct.mean() if "ct" in df.columns else None  # Torque coefficient
        mean_ct = df.cd.mean() if "cd" in df.columns else None  # Thrust coefficient

        print("Performance from {:.1f}--{:.1f} degrees:".format(angle0, df.angle_deg.max()))
        print("Mean TSR: {:.2f}".format(mean_tsr))
        print("Mean Power Coefficient (C_P): {:.4f}".format(mean_cp))
        if mean_ct is not None:
            print("Mean Thrust Coefficient (C_T): {:.4f}".format(mean_ct))
        if mean_cq is not None:
            print("Mean Torque Coefficient (C_Q): {:.4f}".format(mean_cq))

        if self.turbine_model is not None:
            rho = self.turbine_model.fluid.density
            r = self.turbine_model.hub.radius + self.turbine_model.blade.radius
            area = np.pi * r**2
            U = self.turbine_model.fluid.velocity

            # Power
            power = mean_cp * 0.5 * rho * area * U**3

            # Torque from C_Q
            torque = mean_cq * 0.5 * rho * area * U**2 * r if mean_cq is not None else None

            # Thrust from C_T
            thrust = mean_ct * 0.5 * rho * area * U**2 if mean_ct is not None else None

            print("Power: {:.2f} MW".format(power / 1e6))
            if torque is not None:
                print("Torque: {:.2f} MNm".format(torque / 1e6))
            if thrust is not None:
                print("Thrust: {:.2f} MN".format(thrust / 1e6))
        else:
            print("Turbine model not provided, cannot calculate performance metrics.")

        return None

    def plot_cp(self, angle0=2160.0):
        """Plot the power coefficient as a function of azimuthal angle.

        Args:
            angle0 (float, optional): Angle. Defaults to 2160.0.
        """
        # Make a copy of the turbine data and drop duplicate time values, only keeping the last value
        df = self.turbine_df.copy()
        df = df.drop_duplicates("time", keep="last")

        # Sort the values by azimuthal angle
        if df.angle_deg.max() < angle0:
            angle0 = 0.0

        # Plot the power coefficient as a function of azimuthal angle
        plt.plot(df.angle_deg, df.cp)
        plt.xlabel("Azimuthal angle (degrees)")
        plt.ylabel("$C_P$")
        plt.tight_layout()

        # Save the plot
        plt.savefig(self.case_dir / "postProcessing" / "turbines_0_cp.png")

    def extract_spanwise_data(self):
        """Extract the spanwise data from the simulation results.

        Returns:
            dict: A dictionary of ElementData class objects containing the spanwise data for each element.
        """
        # Format the case directory
        elements_dir: Path = self.case_dir / "postProcessing" / "actuatorLineElements" / "0"

        # Create a dictionary to store DataFrames for each element file
        element_dict = {}

        # Iterate over all element files that match the pattern
        for element_file in elements_dir.glob("turbine.blade1.element*.csv"):
            # Extract the element number from the file name (e.g., "element1" from "turbine.blade1.element1.csv")
            element_number = int(element_file.stem.replace("turbine.blade1.element", ""))  # "turbine.blade1.element1"

            # Read the CSV file into a DataFrame
            df = pd.read_csv(element_file)

            # Store the DataFrame in the dictionary, using the element name as the key
            element_dict[element_number] = ElementData(element_number, df)

        return element_dict

    def plot_spanwise(self):
        """Plot spanwise distribution of angle of attack and relative velocity.
        """
        root_dist = np.zeros(len(self.spanwise_dict))
        urel = np.zeros(len(self.spanwise_dict))
        alpha_deg = np.zeros(len(self.spanwise_dict))
        f = np.zeros(len(self.spanwise_dict))
        cl = np.zeros(len(self.spanwise_dict))

        for idx, element in self.spanwise_dict.items():
            root_dist[element.element_number] = element.root_dist
            urel[element.element_number] = element.urel
            alpha_deg[element.element_number] = element.alpha_deg
            f[element.element_number] = element.f
            cl[element.element_number] = element.cl
        fig, ax = plt.subplots(nrows=1, ncols=2, figsize=(7.5, 3.25))
        ax[0].plot(root_dist, cl)
        ax[0].set_ylabel(r"$C_l$")
        ax[1].plot(root_dist, f)
        ax[1].set_ylabel(r"$f$")
        for a in ax:
            a.set_xlabel("$r/R$")
        fig.tight_layout()

        # Save the plot
        plt.savefig(self.case_dir / "postProcessing" / "turbines_0_spanwise.png")

    def plot_element_time_series(self, element_number):
        """Plot the time series data for a specific element.

        Args:
            element_number (int): The element number to plot.
        """
        def plot_time_dependent_data(df):
            """Plot the time-dependent data from the simulation results.
            """
            # Time dependent data is already extracted from self.spanwise_dict
            # Plot the time series data for the specified element
            fig, ax = plt.subplots(nrows=2, ncols=2, figsize=(7.5, 5))

            ax: plt.Axes = ax
            fig: plt.Figure = fig

            ax[0, 0].plot(df.time, df.rel_vel_mag)
            ax[0, 0].set_ylabel("$U_{rel}$ (m/s)")
            ax[0, 1].plot(df.time, df.alpha_deg)
            ax[0, 1].set_ylabel(r"$\alpha$ (degrees)")
            ax[1, 0].plot(df.time, df.cl)
            ax[1, 0].set_ylabel("$C_l$")
            ax[1, 1].plot(df.time, df.end_effect_factor)
            ax[1, 1].set_ylabel("$f$")
            for a in ax.flatten():
                a.set_xlabel("Time (s)")
            fig.tight_layout()

            # Save the plot
            plt.savefig(self.case_dir / "postProcessing" / f"turbines_0_time_series_{element_number}.png")

            # Close the plot
            plt.close()

            return None

        # Extract the DataFrame for the specified element
        element = self.spanwise_dict[element_number]

        # Make a copy of the DataFrame
        df: pd.DataFrame = element.df.copy()

        # Plot the time series data for the specified element
        plot_time_dependent_data(df)

        return None


if __name__ == "__main__":
    post = AxialFlowPostProcessing("test_case")
    post.plot_cp()
    post.plot_spanwise()
    for element_number in range(1, len(post.spanwise_dict)):
        post.plot_element_time_series(element_number)
