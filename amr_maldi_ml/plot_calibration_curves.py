"""Plot calibration curves.

The purpose of this script is to plot the calibration curves of
different classifiers to show to what extent calibration can be
used to improve classification results. The script is smart and
will collect data automatically so that plots are created based
on their availability.
"""


import argparse
import collections
import json
import os

from sklearn.calibration import calibration_curve
from sklearn.metrics import accuracy_score
from sklearn.metrics import average_precision_score
from sklearn.metrics import roc_auc_score

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
import seaborn as sns

from tqdm import tqdm


# Global metadata information; this will be updated by the script to
# ensure that we are working with data files from the *same* sources
# in order to create curves.
metadata_versions = {}


def _add_or_compare(metadata):
    if not metadata_versions:
        metadata_versions.update(metadata)
    else:
        # Smarter way to compare the entries of the dictionaries with
        # each other.
        assert metadata_versions == metadata


def plot_calibration_curves(df, output):
    """Plot calibration curves based on data frame.

    This function is performing the main work for a single data frame.
    It will automatically collect the relevant curves and prepare a plot
    according to the data.

    Parameters
    ----------
    df : `pandas.DataFrame`
        TBD

    Returns
    -------
    Nothing. As a side-effect of calling this function, plots will be
    generated.
    """
    # Will store the individual curves for subsequent plotting. Every
    # curve is indexed by a classifier.
    curves = {}

    # The way the data are handed over to this function, there is only
    # a single antibiotic and a single species.
    antibiotic = df.antibiotic.unique()[0]
    species = df.species.unique()[0]

    for model, df_ in df.groupby(['model']):

        y_test = np.vstack(df_['y_test']).ravel()
        y_score = np.vstack(df_['y_score_calibrated'])

        minority_class = np.argmin(np.bincount(y_test))

        prob_true, prob_pred = calibration_curve(y_test,
                                                 y_score[:, minority_class],
                                                 n_bins=10)

        # Note the change in inputs here; it is customary to show the
        # predicted probabilities on the x axis.
        curves[model] = prob_pred, prob_true

    sns.set(style='whitegrid')

    fig, ax = plt.subplots()
    fig.suptitle(f'{species} ({antibiotic})')

    palette = sns.color_palette()

    # To improve the captions of the curves. The advantage of this
    # dictionary is that the script automatically raises an error
    # upon encountering an unknown model.
    model_to_name = {
        'lr': 'Logistic regression',
        'rf': 'Random forest',
        'svm-rbf': 'SVM (RBF kernel)',
        'svm-linear': 'SVM (linear kernel)',
        'lightgbm': 'LightGBM'
    }

    model_to_colour = {
        model: palette[i] for i, model in enumerate(model_to_name)
    }

    for model, curve in curves.items():

        colour = model_to_colour[model]

        ax.plot(
            curve[0],
            curve[1],
            c=colour,
            label=model,
        )

    ax.plot([0, 1], [0, 1], 'k:', label='Perfectly calibrated')

    ax.set_xlabel('Mean predicted probability')
    ax.set_ylabel('True probability')
    ax.set_xlim((0, 1))
    ax.set_ylim((0, 1))
    ax.set_aspect('equal')
    ax.legend(loc='lower right')

    plt.savefig(
        os.path.join(output,
                     f'calibration_{species}_{antibiotic}.png'),
        bbox_inches='tight'
    )
    plt.show()


def plot_rejection_curves(df):
    """Plot rejection curves based on data frame.

    This function simulates different rejection scenarios based on the
    classifier scores. It will calculate rejection curves and plot the
    different scenarios in the data frame.

    Parameters
    ----------
    df : `pandas.DataFrame`
        TBD

    Returns
    -------
    Nothing. As a side-effect of calling this function, plots will be
    generated.
    """
    # Will store the individual curves for subsequent plotting. Every
    # curve is indexed by a classifier.
    curves = {}

    # The way the data are handed over to this function, there is only
    # a single antibiotic and a single species.
    antibiotic = df.antibiotic.unique()[0]
    species = df.species.unique()[0]

    thresholds = np.linspace(0.5, 1.0, 20, endpoint=True)

    for model, df_ in df.groupby(['model']):

        y_test = np.vstack(df_['y_test']).ravel()
        y_score = np.vstack(df_['y_score_calibrated'])
        y_score_max = np.amax(y_score, axis=1)

        minority_class = np.argmin(np.bincount(y_test))

        # Will be filled with the `x` and `y` values of the current curve
        x = []
        y = []

        for threshold in thresholds:

            # Get the indices that we want to *keep*, i.e. those test
            # samples whose maximum probability exceeds the threshold
            indices = y_score_max > threshold

            # Subset the predictions and the labels according to these
            # indices and calculate the desired metric.
            #
            # TODO: make metric configurable
            y_true = y_test[indices]
            y_pred_proba = y_score[indices][:, minority_class]

            # Predict the positive class if the prediction threshold is
            # larger than the one we use for this iteration.
            y_pred = np.zeros_like(y_pred_proba)
            y_pred[y_pred_proba > threshold] = 1.0

            # Ensures that we are working with the proper scenario here;
            # we need two different classes to perform the calculation.
            if len(set(y_true)) != 2:
                break

            average_precision = average_precision_score(y_true, y_pred_proba)
            accuracy = accuracy_score(y_true, y_pred)
            roc_auc = roc_auc_score(y_true, y_pred_proba)

            x.append(threshold)
            y.append(roc_auc)

        curves[model] = x, y

    sns.set(style='whitegrid')

    fig, ax = plt.subplots()
    fig.suptitle(f'{species} ({antibiotic})')

    palette = sns.color_palette()

    # To improve the captions of the curves. The advantage of this
    # dictionary is that the script automatically raises an error
    # upon encountering an unknown model.
    model_to_name = {
        'lr': 'Logistic regression',
        'rf': 'Random forest',
        'svm-rbf': 'SVM (RBF kernel)',
        'svm-linear': 'SVM (linear kernel)',
        'lightgbm': 'LightGBM'
    }

    model_to_colour = {
        model: palette[i] for i, model in enumerate(model_to_name)
    }

    for model, curve in curves.items():

        colour = model_to_colour[model]

        ax.plot(
            curve[0],
            curve[1],
            c=colour,
            label=model,
        )

    ax.set_xlabel('Mean predicted probability')
    ax.set_ylabel('True probability')
    ax.set_xlim((0.5, 1))
    ax.legend(loc='lower right')

    #plt.savefig(
    #    os.path.join(output,
    #                 f'calibration_{species}_{antibiotic}.png'),
    #    bbox_inches='tight'
    #)
    plt.show()



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('INPUT', type=str, help='Input directory')
    parser.add_argument(
        '--output',
        type=str,
        default='.',
        help='Output directory'
    )

    args = parser.parse_args()

    # Stores data rows corresponding to individual scenarios. Each
    # scenario involves the same antibiotic (used as the key here).
    scenarios = collections.defaultdict(list)

    # Keys to skip when creating a single row in the data dictionary
    # above. This ensures that we only add single pieces of data and
    # have an easier time turning every scenario into a data frame.
    skip_keys = ['years', 'metadata_versions']

    files_to_load = []
    for root, dirs, files in os.walk(args.INPUT):
        files_to_load.extend([
            os.path.join(root, fn) for fn in files if
            os.path.splitext(fn)[1] == '.json'
        ])

    for filename in tqdm(files_to_load, desc='File'):

        with open(filename) as f:
            data = json.load(f)

        antibiotic = data['antibiotic']
        species = data['species']

        _add_or_compare(data['metadata_versions'])

        row = {
            key: data[key] for key in data.keys() if key not in skip_keys
        }

        basename = os.path.basename(filename)

        scenarios[(antibiotic, species)].append(row)

    for antibiotic, species in sorted(scenarios.keys()):

        rows = scenarios[(antibiotic, species)]
        df = pd.DataFrame.from_records(rows)

        #plot_calibration_curves(df, args.output)
        plot_rejection_curves(df)
