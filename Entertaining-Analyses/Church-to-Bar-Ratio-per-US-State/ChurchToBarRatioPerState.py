#
# load useful libraries
#
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET
from python_tools_and_shortcuts.math.regressions import regression_first_order

#
# Define a class for conducting per-state "Church to Bar Ratio"
# calculations and analyses
#
class ChurchToBarRatioPerState():

    #
    # constructor
    #
    def __init__(
        self,
        fips : FipsState,
        cbp : CountyBusinessPatternsState,
        filename_state_map_svg : str,
        directory_output : str,
        compute_everything : bool = True,
        naics_drinking_places : str = '722410',
        naics_religious_organizations : str = '813110',
        url_svg_namespace : str = 'http://www.w3.org/2000/svg',
        list_colors : list = [
            '#010338', '#02184a', '#032d5c', '#05426e',
            '#065780', '#076c92', '#0881a5', '#0996b7',
            '#0aabc9', '#0cc0db', '#0dd5ed', '#0eeaff',
        ],
    ):
        #
        # store function arguments into the object
        #
        self.df_fips_codes = fips.df.copy()
        self.df_cbp = cbp.df[['fipstate', 'naics', 'emp', 'est']].copy()
        self.filename_state_map_svg = filename_state_map_svg
        self.directory_output = directory_output
        self.naics_drinking_places = naics_drinking_places
        self.naics_religious_organizations = naics_religious_organizations
        self.url_svg_namespace = url_svg_namespace
        self.list_colors = list_colors

        #
        # initialize interval object attributes
        #
        self.dict_aggregated = {}

        #
        # Adjust data types
        #
        self.df_cbp['emp'] = self.df_cbp['emp'].astype('Int64')
        self.df_cbp['est'] = self.df_cbp['est'].astype('Int64')

        #
        # Run the full computations automatically if True
        #
        if compute_everything:
        
            #
            # Identify the distinct geographies we are working with
            #
            self.extract_unique_geographical_identifiers()

            #
            # Keep only the NAICS codes we are considering
            #
            self.filter_by_industry()

            #
            # aggregate establishment and employee counts
            #
            self.aggregate('emp')
            self.aggregate('est')

            #
            # Join the separate aggregated dataframes
            #
            self.separate_aggregated_dataframes()
        
            #
            # Reorganize the dataframe to get both NAICS on the same row,
            # so that each state has a single row
            #
            self.reorganize_dataframe_to_get_one_row_per_state()

            #
            # ensure all geographical locations are represented
            #
            self.ensure_all_geographic_locations_are_represented()

            #
            # QA #1
            #
            self.run_qa_1()
        
            #
            # add state codes
            #
            self.add_state_codes()

            #
            # compute ratio
            #
            self.compute_ratio()

            #
            # log10 transform
            #
            self.compute_log10_transform()

            #
            # Define color groups and state coloration
            #
            self.define_color_group_cutpoints()
            self.define_color_groups()

            #
            # QA #2
            #
            self.run_qa_2()

            #
            # Create the CSS required to color the states in the SVG maps
            #
            self.create_color_css()

            #
            # Create the final SVG maps
            #
            self.create_SVG_maps()

    #
    # Identify the distinct geographies we are working with
    #
    def extract_unique_geographical_identifiers(self):
        self.df_all_geo = (
            self.df_cbp[['fipstate']]
            .drop_duplicates()
            .sort_values(by = ['fipstate'])
            .copy()
            .reset_index(drop = True)
        )

    #
    # Keep only the NAICS codes we are considering
    #
    def filter_by_industry(self):
        naics_list = [self.naics_drinking_places, self.naics_religious_organizations]
        self.df_naics = self.df_cbp[self.df_cbp['naics'].isin(naics_list)].copy()

    #
    # aggregate establishment and employee counts
    #
    def aggregate(self, column_to_use):
        df_agg = (
            self.df_naics
            .groupby(['fipstate', 'naics'])
            [column_to_use]
            .agg(
                'sum'
            )
            .reset_index()
        )
        self.dict_aggregated[column_to_use] = df_agg

    #
    # Join the separate aggregated dataframes
    #
    def separate_aggregated_dataframes(self):
        list_keys = sorted(list(self.dict_aggregated.keys()))
        self.df_agg = self.dict_aggregated[list_keys[0]]
        for key in list_keys[1:]:
            self.df_agg = pd.merge(self.df_agg, self.dict_aggregated[key], on = ['fipstate', 'naics'], how = 'left')

    #
    # Reorganize the dataframe to get both NAICS on the same row,
    # so that each state has a single row
    #
    def reorganize_dataframe_to_get_one_row_per_state(self):
        self.df_joined = pd.merge(
            (
                self.df_agg[self.df_agg['naics'] == self.naics_drinking_places]
                .drop(columns = ['naics'])
                .rename(
                    columns = {
                        'emp' : 'n_emp_drinking',
                        'est' : 'n_est_drinking',    
                    }
                )
            ),
            (
                self.df_agg[self.df_agg['naics'] == self.naics_religious_organizations]
                .drop(columns = ['naics'])
                .rename(
                    columns = {
                        'emp' : 'n_emp_religious',
                        'est' : 'n_est_religious',    
                    }
                )
            ),
            on = ['fipstate'],
            how = 'left',
        )

    #
    # ensure all geographical locations are represented
    #
    def ensure_all_geographic_locations_are_represented(self):
        self.df_all_geo_joined = (
            pd.merge(
                self.df_all_geo,
                self.df_joined,
                on = ['fipstate'],
                how = 'left',
            )
            .sort_values(by = ['fipstate'])
        )

    #
    # QA #1
    #
    # To ensure there are no null values in the dataframe
    #
    def run_qa_1(self):
        assert len(self.df_all_geo_joined.index) == len(self.df_all_geo_joined.dropna().index)

    #
    # add state codes
    #
    def add_state_codes(self):
        self.df = (
            pd.merge(
                self.df_all_geo_joined,
                (
                    self.df_fips_codes
                    .rename(
                        columns = {
                            'STATE' : 'state',
                            'STATEFP' : 'fipstate',
                        }
                    )
                ),
                on = ['fipstate'],
                how = 'left',
            )
            .sort_values(by = ['fipstate'])
            .reset_index(drop = True)
        )

    #
    # compute church to bar ratio
    #
    def compute_ratio(self):
        for column_root in ['emp', 'est']:
            self.df['c2br_' + column_root] = (
                self.df['n_' + column_root + '_religious'] / 
                    self.df['n_' + column_root + '_drinking']
            )

    #
    # log transform
    #
    def compute_log10_transform(self):
        for column_type in ['emp', 'est']:
            self.df['log10_c2br_' + column_type] = np.log10(self.df['c2br_' + column_type])
            
    #
    # plot count histograms
    #
    def plot_count_histograms(self, column_type, column_naics, title):
        plt.figure(figsize = [10, 4])
        
        plt.subplot(1, 2, 1)
        plt.hist(self.df['n_' + column_type + '_' + column_naics])
        plt.title('Histogram\n' + title)
        plt.xlabel(title)
        plt.ylabel('Count of States')

        plt.subplot(1, 2, 2)
        plt.hist(np.log10(self.df['n_' + column_type + '_' + column_naics]))
        plt.title('Histogram\n' + 'Log10( ' + title + ' )')
        plt.xlabel('Log10( ' + title + ' )')
        plt.ylabel('Count of States')
        
        plt.show()
        plt.close()

    #
    # plot ratio histograms
    #
    def plot_ratio_histograms(self, column_type, title):
        plt.figure(figsize = [10, 4])
        
        plt.subplot(1, 2, 1)
        plt.hist(self.df['c2br_' + column_type])
        plt.title('Histogram\n' + title)
        plt.xlabel(title)
        plt.ylabel('Count of States')

        plt.subplot(1, 2, 2)
        plt.hist(np.log10(self.df['c2br_' + column_type]))
        plt.title('Histogram\n' + 'Log10( ' + title + ' )')
        plt.xlabel('Log10( ' + title + ' )')
        plt.ylabel('Count of States')
        
        plt.show()
        plt.close()

    #
    # plot counts
    #
    def plot_counts_vs(self):
        plt.figure(figsize = [10, 4])

        plt.subplot(1, 2, 1)
        x = np.log10(self.df['n_est_drinking'].values)
        y = np.log10(self.df['n_est_religious'].values)
        df_regression, r_adj = regression_first_order(x, y)
        plt.plot(x, y, '.')
        plt.plot(df_regression['x'], df_regression['y_predicted'], label = 'R_adj = %0.2f' % r_adj)
        plt.xlabel('Log10( Number of Drinking Establishments )')
        plt.ylabel('Log10( Number of Religious Establishments )')
        plt.title('Establishment Counts: Religious vs. Drinking')
        plt.legend()
        
        plt.subplot(1, 2, 2)
        x = np.log10(self.df['n_emp_drinking'].values)
        y = np.log10(self.df['n_emp_religious'].values)
        df_regression, r_adj = regression_first_order(x, y)
        plt.plot(x, y, '.')
        plt.plot(df_regression['x'], df_regression['y_predicted'], label = 'R_adj = %0.2f' % r_adj)
        plt.xlabel('Log10( Number of Drinking Employees )')
        plt.ylabel('Log10( Number of Religious Employees )')
        plt.title('Employee Counts: Religious vs. Drinking')
        plt.legend()
        
        plt.show()
        plt.close()

    #
    # plot ratios
    #
    def plot_ratio_vs(self):
        plt.figure()

        x = np.log10(self.df['c2br_emp'].values)
        y = np.log10(self.df['c2br_est'].values)
        df_regression, r_adj = regression_first_order(x, y)
        plt.plot(x, y, '.')
        plt.plot(df_regression['x'], df_regression['y_predicted'], label = 'R_adj = %0.2f' % r_adj)
        plt.xlabel('Log10( Church to Bar Ratio by Employee Counts )')
        plt.ylabel('Log10( Church to Bar Ratio by Establishment Counts )')
        plt.title('Church to Bar Ratio\nComputed by Establishment Count vs.\nComputed by Employee Count')
        plt.legend()
        
        plt.show()
        plt.close()

    #
    # we divide the range of log10 ratios into a series of cutpoints
    #
    def define_color_group_cutpoints(self):
        self.dict_per_column_cutpoints = {}
        for column in ['log10_c2br_emp', 'log10_c2br_est']:
            the_min = np.min(self.df[column])
            the_max = np.max(self.df[column])
            color_interval = (the_max - the_min) / len(self.list_colors)
            
            cutpoints = []
            for i in range(0, len(self.list_colors)):
                start = color_interval * i + the_min
                end = color_interval * (i + 1) + the_min
                cutpoints.append(
                    {
                        'index' : i,
                        'start' : start,
                        'end' : end,
                    }
                )

            self.dict_per_column_cutpoints[column] = cutpoints

    #
    # using the cutpoints computed above, we specify
    # each state's coloration group
    #
    def define_color_groups(self):

        #
        # define a function to test membership in color group value range
        #
        def assign_color_group(value, cutpoints):
            to_return = None
            for item in cutpoints:
                if value >= item['start'] and value <= item['end']:
                    return item['index']
            
            # deal with precision-related error
            if value > item['end']:
                return item['index']

        for column in self.dict_per_column_cutpoints.keys():
            cutpoints = self.dict_per_column_cutpoints[column]

            self.df['color_group_' + column] = [
                int(assign_color_group(x, cutpoints)) for x in self.df[column]
            ]

            self.df['color_' + column] = [
                self.list_colors[i] for i in self.df['color_group_' + column]
            ]

        list_color_columns = ['state']
        list_color_columns.extend(['color_' + x for x in self.dict_per_column_cutpoints.keys()])
        self.df_colors = self.df[list_color_columns].copy()
        self.df_colors.columns = [x.replace('color_log10_c2br_', '') for x in self.df_colors.columns]

    #
    # A second QA to ensure there are no null values in the dataframe
    #
    def run_qa_2(self):
        assert len(self.df_colors.index) == len(self.df_colors.dropna().index)

    #
    # Create the CSS for the SVG maps to facilitate state coloration
    #
    def create_color_css(self):
        self.dict_state_color_lists = {}
        for column in ['emp', 'est']:
            self.dict_state_color_lists[column] = (
                self
                .df_colors
                .groupby([column])
                ['state']
                .agg(list)
                .reset_index()
            )

        for column in ['emp', 'est']:
            df = self.dict_state_color_lists[column]

            list_css = []
            for i, row in df.iterrows():
                css = (
                    ','.join(
                        ['.' + x.lower() for x in row['state']]
                    ) + ' {fill:' + row[column] + '}'
                )
                list_css.append(css)
            df['css'] = list_css

    #
    # produce the final maps
    #
    def create_SVG_maps(self):
        for column in ['emp', 'est']:
            df = self.dict_state_color_lists[column]

            namespace = {'svg': self.url_svg_namespace}
    
            tree = ET.parse(self.filename_state_map_svg)
            root = tree.getroot()

            style_tag = root.find('.//svg:style', namespace)
    
            if style_tag is not None:
                new_style_tag = style_tag.text + '\n\n' + '\n'.join(list(df['css'].values)) + '\n\n'
                style_tag.text = new_style_tag

            filename_output_svg = self.directory_output + '/' + column.upper() + '_per_us_state_church_to_bar_ratio.svg'
            tree.write(filename_output_svg, encoding='utf-8', xml_declaration=True)