#
# import useful libraries
#
import os
import pandas as pd
from zipfile import ZipFile
from python_tools_and_shortcuts.files.downloading import download_file

#
# a crude list of fields that should be imported from the source data
# as numeric values
#
list_fields_numeric = [
    'EMP', 'QP1', 'AP', 'EST', 'E<5', 'Q<5', 'A<5',
    'E5_9', 'Q5_9', 'A5_9', 
    'E10_19', 'Q10_19', 'A10_19',
    'E20_49', 'Q20_49', 'A20_49',
    'E50_99', 'Q50_99', 'A50_99',
    'E100_249', 'Q100_249', 'A100_249',
    'E250_499', 'Q250_499', 'A250_499',
    'E500_999', 'Q500_999', 'A500_999',
    'E1000', 'Q1000', 'A1000',
]

#
# Define a class to encapsulate the state-level
# County Business Patterns data published by the
# United States Census Bureau
#
class CountyBusinessPatternsState():

    #
    # Constructor
    #
    def __init__(
        self,
        url_per_state_cbp = 'https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23st.zip',
        directory_output = 'output',
    ):
        self.url_per_state_cbp = url_per_state_cbp
        self.directory_output = directory_output
        self.download_state_CBP()
        self.create_dataframe()

    #
    # Download the County Business Patterns data
    #
    def download_state_CBP(self):
        filename = self.url_per_state_cbp.split('/')[-1]
        download_file(self.url_per_state_cbp, self.directory_output)
        
        with ZipFile(self.directory_output + '/' + filename, 'r') as zip_ref:
            self.list_filenames = zip_ref.namelist()
            zip_ref.extractall(path = self.directory_output)

        self.list_filenames = [self.directory_output + '/' + x for x in self.list_filenames]
        os.remove(self.directory_output + '/' + filename)

    #
    # Create a dataframe containing the downloaded data
    #
    def create_dataframe(self):

        def load_file(filename):
            df = (
                pd.read_csv(
                    filename,
                    sep = ',',
                    dtype = {
                        'fipstate' : str,
                        'naics' : str,
                    },
                )
            )
            for column in list_fields_numeric:
                df[column.lower()] = df[column.lower()].astype('Float64')

            os.remove(filename)
            return df

        list_df = [load_file(x) for x in self.list_filenames]
        self.df = pd.concat(list_df)
