#!/usr/bin/env python
#
# Collection script for all results. Will create a table based on the
# species and the antibiotic and summarise the performance measures.

import argparse
import itertools
import json
import os

import numpy as np
import pandas as pd

from tqdm import tqdm


def get_files(directory):
    """Walk a directory structure and return JSON filenames.

    This function is a helper function for finding JSON filenames in
    a recursive fashion, i.e. by fully walking a directory and *all*
    its subdirectories.

    Parameters
    ----------
    directory : str
        Root folder for the directory enumeration

    Returns
    -------
    List of JSON files (ready for reading; the whole path of each file
    will be returned).
    """
    result = []
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if os.path.splitext(filename)[1] == '.json':
                result.append(os.path.join(root, filename))

    return result


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('INPUT', nargs='+', type=str)

    parser.add_argument(
        '-r', '--rank-by',
        type=str,
        help='If set, provides metric by which to rank models. This will '
             'result in calculating a table of ranks instead of a report '
             'on the detailed behaviour of models.',
    )

    parser.add_argument(
        '-i', '--ignore',
        type=str,
        help='If set, ignores files that contain the specified string.'
    )

    args = parser.parse_args()

    metrics = ['auroc', 'auprc', 'accuracy',
               'train_auroc', 'train_auprc', 'train_accuracy']

    rows = []
    filenames = args.INPUT

    # Check if we are getting a directory here, in which case we have to
    # create the list of filenames manually.
    if len(filenames) == 1:
        if os.path.isdir(filenames[0]):
            filenames = get_files(filenames[0])
            filenames = sorted(filenames)

    if args.ignore is not None:
        filenames = [fn for fn in filenames if args.ignore not in fn]

    for filename in tqdm(filenames, desc='Loading'):
        with open(filename) as f:

            # Ensures that we can parse normal JSON files
            pos = 0

            for line in f:

                # We found *probably* the beginning of the JSON file, so
                # we can start the parse process from here, having to do
                # a reset.
                if line.startswith('{'):
                    f.seek(pos)
                    break
                else:
                    pos += len(line)

            # Check whether file is empty for some reason. If so, we
            # skip it.
            line = f.readline()
            if line == '':
                continue

            # Not empty, so we need to reset the file pointer
            else:
                f.seek(pos)

            data_raw = json.load(f)

        # Create one row in the table containing the relevant
        # information for now.
        row = {
            'species': data_raw.get('species', 'all'),
            'antibiotic': data_raw['antibiotic'],
            # If no model was found, default to `lr`. This makes us
            # compatible with older files.
            'model': data_raw.get('model', 'lr'),
        }

        # Check whether information about the train and test site is
        # available. If so, we can automatically stratify accordingly.
        if 'train_site' in data_raw and 'test_site' in data_raw:
            row.update({
                'train_site': data_raw['train_site'],
                'test_site': data_raw['test_site']
            })

        # Ditto for train years.
        if 'train_years' in data_raw and 'test_years' in data_raw:
            row.update({
                'train_years': ' '.join(data_raw['train_years']),
                'test_years': ' '.join(data_raw['test_years'])
            })

        # Check which metrics are *actually* available in the data. This
        # accounts for experiments with specific train/test values, for
        # example.
        metrics_ = list(itertools.chain.from_iterable(
                [[key for key in data_raw if metric in key] for metric
                 in metrics]
        ))

        # No metrics founds; check whether we have folds to traverse and
        # collect the data.
        if len(metrics_) == 0:
            folds = [key for key in data_raw if key.isnumeric()]

            # FIXME: this could be extracted automatically, but it is
            # easier for now. Will patch this later.
            metrics_ = [
                # FIXME: disabled for the time being 'test_source_accuracy',
                'test_source_auprc',
                'test_source_auroc',
                # FIXME: disabled for the time being 'test_target_accuracy',
                'test_target_auprc',
                'test_target_auroc'
            ]

            for fold in folds:
                for metric in metrics_:
                    name = fold.replace('test_', '')
                    name = fold.replace('source', 'src')
                    row.update({
                        'fold': fold.replace('test_', ''),
                        metric: data_raw[fold][metric]
                    })

            metrics = metrics_
        else:
            metrics = sorted(metrics_)

            for metric in metrics:
                row[metric] = data_raw[metric] * 100.0

        rows.append(row)

    pd.options.display.max_rows = 999
    pd.options.display.float_format = '{:,.2f}'.format

    df = pd.DataFrame(rows)

    group_columns = ['species', 'antibiotic', 'model']
    if 'train_site' in df.columns and 'test_site' in df.columns:
        group_columns += ['train_site', 'test_site']
    if 'train_years' in df.columns and 'test_years' in df.columns:
        group_columns += ['train_years', 'test_years']

    # Create a data frame that contains metrics over all the different
    # seeds. Each species--antibiotic combination is represented here.
    df = df.groupby(group_columns).agg(
            {
                metric: [np.mean, np.std] for metric in metrics
            }
        )

    if args.rank_by is not None:
        df = df[args.rank_by][['mean', 'std']]

        # Calculate the ranks on each species--antibiotic combination.
        # If we only have single model here, the result will be '1.0'.
        ranks = df.groupby(['species', 'antibiotic'])['mean'].rank(
            ascending=False,
        )
        ranks.name = 'rank'

        # Create a special 'rank' column and perform the final
        # aggregation based on each model.
        df = pd.concat([df, ranks], axis=1)

        # Figure out how many classifiers we have available for each of
        # the combinations.
        valid_combinations = df.groupby(['species', 'antibiotic']) \
            .size()                                                \
            .reset_index(name='n_classifiers')

        # Keep only valid combinations
        valid_combinations = \
            valid_combinations[valid_combinations['n_classifiers'] > 1]

        # Check which species--antibiotic combinations are left here. We
        # will use this to access our original data frame.
        valid_combinations.set_index(['species', 'antibiotic'], inplace=True)

        # Filter out all invalid columns. We are now left with the ranks
        # of the classifiers along the valid scenarios.
        df = df.reset_index().set_index(['species', 'antibiotic'])
        df = df[df.index.isin(valid_combinations.index)]

        # Finally, calculate the mean value over the measure and over
        # the rank.
        df = df.groupby('model').mean()

    print(df)
