# by Pavlo Bazilinskyy <pavlo.bazilinskyy@gmail.com>
import json
import os
import pandas as pd
import numpy as np
from tqdm import tqdm
import re
import ast
from statistics import mean

import crossing as cs

# warning about partial assignment
pd.options.mode.chained_assignment = None  # default='warn'

logger = cs.CustomLogger(__name__)  # use custom logger


class Heroku:
    # todo: parse browser interactions
    files_data = []  # list of files with heroku data
    heroku_data = pd.DataFrame()  # pandas dataframe with extracted data
    mapping = pd.DataFrame()  # pandas dataframe with mapping
    res = 0  # resolution for keypress data
    save_p = False  # save data as pickle file
    load_p = False  # load data as pickle file
    save_csv = False  # save data as csv file
    # pickle file for saving data
    file_p = 'heroku_data.p'
    # csv file for saving data
    file_data_csv = 'heroku_data'
    # csv file for mapping of stimuli
    file_mapping_csv = 'mapping'
    # keys with meta information
    meta_keys = ['worker_code',
                 'browser_user_agent',
                 'browser_app_name',
                 'browser_major_version',
                 'browser_full_version',
                 'browser_name',
                 'window_height',
                 'window_width',
                 'video_ids']
    # prefixes used for files in node.js implementation
    prefixes = {'stimulus': 'video_'}  # noqa: E501
    # stimulus duration
    default_dur = 0

    def __init__(self,
                 res: int,
                 files_data: list,
                 save_p: bool,
                 load_p: bool,
                 save_csv: bool):
        self.res = res
        self.files_data = files_data
        self.save_p = save_p
        self.load_p = load_p
        self.save_csv = save_csv
        self.num_stimuli = cs.common.get_configs('num_stimuli')
        self.num_repeat = cs.common.get_configs('num_repeat')

    def set_data(self, heroku_data):
        """
        Setter for the data object.
        """
        old_shape = self.heroku_data.shape  # store old shape for logging
        self.heroku_data = heroku_data
        logger.info('Updated heroku_data. Old shape: {}. New shape: {}.',
                    old_shape,
                    self.heroku_data.shape)

    def read_data(self):
        """
        Read data into an attribute.
        """
        # todo: read heroku data
        # load data
        if self.load_p:
            df = cs.common.load_from_p(self.file_p,
                                       'heroku data')
        # process data
        else:
            # read files with heroku data one by one
            data_list = []
            data_dict = {}  # dictionary with data
            for file in self.files_data:
                logger.info('Reading heroku data from {}.', file)
                f = open(file, 'r')
                # add data from the file to the dictionary
                data_list += f.readlines()
                f.close()
            # hold info on previous row for worker
            prev_row_info = pd.DataFrame(columns=['worker_code',
                                                  'time_elapsed'])
            prev_row_info.set_index('worker_code', inplace=True)
            # read rows in data
            for row in tqdm(data_list):  # tqdm adds progress bar
                # use dict to store data
                dict_row = {}
                # load data from a single row into a list
                list_row = json.loads(row)
                # last found stimulus
                stim_name = ''
                # trial last found stimulus
                stim_trial = -1
                # last time_elapsed for logging duration of trial
                elapsed_l = 0
                # record worker_code in the row. assuming that each row has at
                # least one worker_code
                worker_code = [d['worker_code'] for d in list_row['data'] if 'worker_code' in d][0]  # noqa: E501
                # go over cells in the row with data
                for data_cell in list_row['data']:
                    # extract meta info form the call
                    for key in self.meta_keys:
                        if key in data_cell.keys():
                            # piece of meta data found, update dictionary
                            dict_row[key] = data_cell[key]
                            if key == 'worker_code':
                                logger.debug('{}: working with row with data.',
                                             data_cell['worker_code'])
                    # check if stimulus data is present
                    if 'stimulus' in data_cell.keys():
                        # extract name of stimulus after last slash
                        # list of stimuli. use 1st
                        if isinstance(data_cell['stimulus'], list):
                            stim_no_path = data_cell['stimulus'][0].rsplit('/', 1)[-1]  # noqa: E501
                        # single stimulus
                        else:
                            stim_no_path = data_cell['stimulus'].rsplit('/', 1)[-1]  # noqa: E501
                        # remove extension
                        stim_no_path = os.path.splitext(stim_no_path)[0]
                        # Check if it is a block with stimulus and not an
                        # instructions block
                        if (cs.common.search_dict(self.prefixes, stim_no_path)  # noqa: E501
                           is not None):
                            # stimulus is found
                            logger.debug('Found stimulus {}.', stim_no_path)
                            if self.prefixes['stimulus'] in stim_no_path:
                                # Record that stimulus was detected for the
                                # cells to follow
                                stim_name = stim_no_path
                                # record trial of stimulus
                                stim_trial = data_cell['trial_index']
                                # add trial duration
                                if 'time_elapsed' in data_cell.keys():
                                    # positive time elapsed from las cell
                                    if elapsed_l:
                                        time = elapsed_l
                                    # non-positive time elapsed. use value from
                                    # the known cell for worker
                                    else:
                                        time = prev_row_info.loc[worker_code, 'time_elapsed']  # noqa: E501
                                    # calculate duration
                                    dur = float(data_cell['time_elapsed']) - time  # noqa: E501
                                    if stim_name + '-dur' not in dict_row.keys():  # noqa: E501
                                        # first value
                                        dict_row[stim_name + '-dur'] = dur  # noqa: E501
                                    else:
                                        # previous values found
                                        dict_row[stim_name + '-dur'].append(dur)  # noqa: E501
                    # keypresses
                    if 'rts' in data_cell.keys() and stim_name != '':
                        # record given keypresses
                        responses = data_cell['rts']
                        logger.debug('Found {} points in keypress data.',
                                     len(responses))
                        # extract pressed keys and rt values
                        key = [point['key'] for point in responses]
                        rt = [point['rt'] for point in responses]
                        # check if values were recorded previously
                        if stim_name + '-key' not in dict_row.keys():
                            # first value
                            dict_row[stim_name + '-key'] = key
                        else:
                            # previous values found
                            dict_row[stim_name + '-key'].append(key)
                        # check if values were recorded previously
                        if stim_name + '-rt' not in dict_row.keys():
                            # first value
                            dict_row[stim_name + '-rt'] = rt
                        else:
                            # previous values found
                            dict_row[stim_name + '-rt'].append(rt)
                    # questions after stimulus
                    if 'responses' in data_cell.keys() and stim_name != '':
                        # record given keypresses
                        responses = data_cell['responses']
                        logger.debug('Found responses to questions {}.',
                                     responses)
                        # extract pressed keys and rt values
                        responses = ast.literal_eval(re.search('({.+})',
                                                               responses).group(0))  # noqa: E501
                        # unpack questions and answers
                        questions = []
                        answers = []
                        for key, value in responses.items():
                            questions.append(key)
                            answers.append(value)
                        # check if values were recorded previously
                        if stim_name + '-qs' not in dict_row.keys():
                            # first value
                            dict_row[stim_name + '-qs'] = questions
                        else:
                            # previous values found
                            dict_row[stim_name + '-qs'].append(questions)
                        # Check if time spent values were recorded
                        # previously
                        if stim_name + '-as' not in dict_row.keys():
                            # first value
                            dict_row[stim_name + '-as'] = answers
                        else:
                            # previous values found
                            dict_row[stim_name + '-as'].append(answers)
                    # browser interaction events
                    if 'interactions' in data_cell.keys() and stim_name != '':
                        interactions = data_cell['interactions']
                        logger.debug('Found {} browser interactions.',
                                     len(interactions))
                        # extract events and timestamps
                        event = []
                        time = []
                        for interation in interactions:
                            if interation['trial'] == stim_trial:
                                event.append(interation['event'])
                                time.append(interation['time'])
                        # Check if inputted values were recorded previously
                        if stim_name + '-event' not in dict_row.keys():
                            # first value
                            dict_row[stim_name + '-event'] = event
                        else:
                            # previous values found
                            dict_row[stim_name + '-event'].append(event)
                        # check if values were recorded previously
                        if stim_name + '-time' not in dict_row.keys():
                            # first value
                            dict_row[stim_name + '-time'] = time
                        else:
                            # previous values found
                            dict_row[stim_name + '-time'].append(time)
                    # questions in the end
                    if 'responses' in data_cell.keys() and stim_name == '':
                        # record given keypresses
                        responses = data_cell['responses']
                        logger.debug('Found responses to final questions {}.',
                                     responses)
                        # extract pressed keys and rt values
                        responses = ast.literal_eval(re.search('({.+})',
                                                               responses).group(0))  # noqa: E501
                        # unpack questions and answers
                        questions = []
                        answers = []
                        for key, value in responses.items():
                            questions.append(key)
                            answers.append(value)
                        # Check if inputted values were recorded previously
                        if 'end-qs' not in dict_row.keys():
                            dict_row['end-qs'] = questions
                            dict_row['end-as'] = answers
                    # record last time_elapsed
                    if 'time_elapsed' in data_cell.keys():
                        elapsed_l = float(data_cell['time_elapsed'])
                # update last time_elapsed for worker
                prev_row_info.loc[dict_row['worker_code'], 'time_elapsed'] = elapsed_l  # noqa: E501
                # worker_code was ecnountered before
                if dict_row['worker_code'] in data_dict.keys():
                    # iterate over items in the data dictionary
                    for key, value in dict_row.items():
                        # new value
                        if key not in data_dict[dict_row['worker_code']].keys():  # noqa: E501
                            data_dict[dict_row['worker_code']][key] = value
                        # update old value
                        else:
                            # udpate only if it is a list
                            if isinstance(data_dict[dict_row['worker_code']][key], list):  # noqa: E501
                                # traverse repetition ids untill get new
                                # repetition
                                for rep in range(1, self.num_repeat):
                                    # build new key with id of repetition
                                    # (starting from 1)
                                    new_key = key + '-' + str(rep)
                                    if new_key not in data_dict[dict_row['worker_code']].keys():  # noqa: E501
                                        data_dict[dict_row['worker_code']][new_key] = value  # noqa: E501
                # worker_code is ecnountered for the first time
                else:
                    data_dict[dict_row['worker_code']] = dict_row
            # turn into pandas dataframe
            df = pd.DataFrame(data_dict)
            df = df.transpose()
            # report people that attempted study
            unique_worker_codes = df['worker_code'].drop_duplicates()
            logger.info('People who attempted to participate: {}',
                        unique_worker_codes.shape[0])
            # filter data
            df = self.filter_data(df)
            # sort columns alphabetically
            df = df.reindex(sorted(df.columns), axis=1)
            # move worker_code to the front
            worker_code_col = df['worker_code']
            df.drop(labels=['worker_code'], axis=1, inplace=True)
            df.insert(0, 'worker_code', worker_code_col)
        # save to pickle
        if self.save_p:
            cs.common.save_to_p(self.file_p, df, 'heroku data')
        # save to csv
        if self.save_csv:
            # todo: check whith index=False is needed here
            df.to_csv(cs.settings.output_dir + '/' + self.file_data_csv +
                      '.csv', index=False)
            logger.info('Saved heroku data to csv file {}',
                        self.file_data_csv + '.csv')
        # update attribute
        self.heroku_data = df
        # return df with data
        return df

    def read_mapping(self):
        """
        Read mapping.
        """
        # read mapping from a csv file
        df = pd.read_csv(cs.common.get_configs('mapping_stimuli'))
        # set index as stimulus_id
        df.set_index('video_id', inplace=True)
        # update attribute
        self.mapping = df
        # return mapping as a dataframe
        return df

    def process_kp(self):
        """Process keypresses for resolution self.res.

        Returns:
            mapping: updated mapping df.
        """
        # array to store all binned rt data in
        mapping_rt = []
        # loop through all videos
        for i in range(0, self.num_stimuli):
            video_kp = []
            for rep in range(self.num_repeat):
                # 0th repetition has no suffix with repetition ID
                if rep == 0:
                    video_rt = 'video_' + str(i) + '-rt'
                # add suffix with repetition ID
                else:
                    video_rt = 'video_' + str(i) + '-rt-' + str(rep)
                video_len = self.mapping.loc['video_' + str(i)]['video_length']
                rt_data = []
                counter_data = 0
                for (col_name, col_data) in self.heroku_data.iteritems():
                    # find the right column to loop through
                    if video_rt == col_name:
                        # loop through rows in column
                        for row in col_data:
                            # check if data is string to filter out nan data
                            # print('row', row)
                            if type(row) == list:
                                # saving amount of times the video has been
                                # watched
                                counter_data = counter_data + 1
                                # if list contains only one value, append to
                                # rt_data
                                if len(row) == 1:
                                    rt_data.append(row[0])
                                # if list contains more then one value, go
                                # through list to remove keyholds
                                elif len(row) > 1:
                                    for j in range(1, len(row)):
                                        # if time between 2 stimuli is more
                                        # than 35 ms, add to array (no hold)
                                        if row[j] - row[j - 1] > 35:
                                            # append buttonpress data to rt
                                            # array
                                            rt_data.append(row[j])
                        # if all data for one video was found, divide them in
                        # bins
                        kp = []
                        # loop over all bins, dependent on resolution
                        for rt in range(self.res, video_len + self.res,
                                        self.res):
                            bin_counter = 0
                            for data in rt_data:
                                # go through all video data to find all data
                                # within
                                # specific bin
                                if rt - self.res < data <= rt:
                                    # if data is found, up bin counter
                                    bin_counter = bin_counter + 1
                            percentage = bin_counter / counter_data
                            kp.append(round(percentage * 100))
                        # store keypresse from repetition
                        video_kp.append(kp)
                        break
            # calculate mean keypresse from all repetitions
            kp_mean = [*map(mean, zip(*video_kp))]
            # append data from one video to the mapping array
            mapping_rt.append(kp_mean)
        # update own mapping to include keypress data
        self.mapping['kp'] = mapping_rt
        # save to csv
        if self.save_csv:
            # save to csv
            self.mapping.to_csv(cs.settings.output_dir + '/' +
                                self.file_mapping_csv + '.csv')
        # return new mapping
        return self.mapping

    def filter_data(self, df):
        """
        Filter data based on the folllowing criteria:
            1. People who entered incorrect codes for sentinel images more than
               cs.common.get_configs('allowed_mistakes_sent') times.
        """
        # more than allowed number of mistake with codes for sentinel images
        # load mapping of codes and coordinates
        logger.info('Filtering heroku data.')
        # df to store data to filter out
        df_1 = pd.DataFrame()
        # concatanate dfs with filtered data
        old_size = df.shape[0]
        # people to filter present
        if df_1.shape[0] != 0:
            df_filtered = pd.concat([df_1])
            # drop rows with filtered data
            unique_worker_codes = df_filtered['worker_code'].drop_duplicates()
            df = df[~df['worker_code'].isin(unique_worker_codes)]
        logger.info('Filtered in total in heroku data: {}',
                    old_size - df.shape[0])
        return df

    def show_info(self):
        """
        Output info for data in object.
        """
        logger.info('No info to show.')
