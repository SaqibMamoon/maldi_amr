"""Measure ensemble training performance.

The purpose of this script is to measure ensemble training performance,
i.e. the performance that we obtain by *training* on all species, but
evaluating only on a single one (which gives us more data, but also a
higher variance to contend with). This is contrasted by the usual
training scenario, where we train on specific species and evaluate on it
as well.

This script reproduces Figure 3 in the main paper.
"""

import argparse
import dotenv
import joblib
import logging
import os
import json
import pathlib
import warnings

import numpy as np

from maldi_learn.driams import DRIAMSDatasetExplorer
from maldi_learn.driams import DRIAMSLabelEncoder

from maldi_learn.driams import load_driams_dataset

from maldi_learn.utilities import stratify_by_species_and_label

from utilities import generate_output_filename

from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.metrics import average_precision_score
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.preprocessing import StandardScaler

dotenv.load_dotenv()
DRIAMS_ROOT = os.getenv('DRIAMS_ROOT')

# These parameters should remain fixed for this particular
# experiment. We always train on the same data set, using
# *all* available years.
site = 'DRIAMS-A'
years = ['2015']  # TODO: , '2016', '2017', '2018']


def subset_indices(y, indices, species):
    """Calculate subset of species-relevant indices and labels.

    The purpose of this function is to return a set of labels for use
    in a downstream classification task, based on a prior *selection*
    of indices.

    Parameters
    ----------
    y : `pandas.DataFrame`
        Data frame containing labels and species information. Must have
        a 'species' column to be valid.

    indices : array-like, int
        Indices (integer-based) referring to valid positions within the
        label vector `y`.

    species : str
        Identifier of a species whose subset of labels should be
        calculated.

    Returns
    -------
    Tuple of indices (array of length n, where n is the number of
    samples) and subset of data frame. The indices correspond to the
    subset of species-specific indices. The subset can be used for
    accessing vectors of spectra.
    """

    y = y.iloc[indices].copy()
    y.index = indices
    y = y.query('species == @args.species')

    indices = y.index.values
    return indices, y


if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-a', '--antibiotic',
        type=str,
        help='Antibiotic for which to run the experiment',
        required=True,
    )

    parser.add_argument(
        '-s', '--species',
        type=str,
        help='Species for which to run the experiment',
        required=True
    )

    parser.add_argument(
        '-S', '--seed',
        type=int,
        help='Random seed to use for the experiment',
        required=True
    )

    name = 'fig3_ensemble'

    parser.add_argument(
        '-o', '--output',
        default=pathlib.Path(__file__).resolve().parent.parent / 'results'
                                                               / name,
        type=str,
        help='Output path for storing the results.'
    )

    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='If set, overwrites all files. Else, skips existing files.'
    )

    args = parser.parse_args()

    # Create the output directory for storing all results of the
    # individual combinations.
    os.makedirs(args.output, exist_ok=True)

    # Basic log configuration to ensure that we see where the process
    # spends most of its time.
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(message)s'
    )

    explorer = DRIAMSDatasetExplorer(DRIAMS_ROOT)
    metadata_fingerprints = explorer.metadata_fingerprints(site)

    logging.info(f'Site: {site}')
    logging.info(f'Years: {years}')
    logging.info(f'Seed: {args.seed}')
    logging.info(f'Antibiotic: {args.antibiotic}')
    logging.info(f'Species: {args.species}')

    driams_dataset = load_driams_dataset(
        DRIAMS_ROOT,
        site,
        years,
        '*',   # This is correct; we initially want *all* species
        antibiotics=args.antibiotic,
        encoder=DRIAMSLabelEncoder(),
        handle_missing_resistance_measurements='remove_if_all_missing',
        spectra_type='binned_6000',
    )

    logging.info(f'Loaded data set')

    # Create feature matrix from the binned spectra. We only need to
    # consider the second column of each spectrum for this.
    X = np.asarray([spectrum.intensities for spectrum in driams_dataset.X])

    # Do the split only once in order to ensure that we are
    # predicting on the same samples subsequently.
    train_index, test_index = stratify_by_species_and_label(
        driams_dataset.y,
        antibiotic=args.antibiotic,
        random_state=args.seed,
    )

    # Required only once because we have to use the *same* indices in
    # the downstream classification task.
    test_index_, y_test = subset_indices(
        driams_dataset.y,
        test_index,
        args.species
    )

    # Actual label vector (`y_test` is a data frame prior to the call of
    # this function)
    y_test = driams_dataset.to_numpy(args.antibiotic, y=y_test)

    for ensemble in [True, False]:

        # Not in ensemble mode; select all samples with the proper
        # species that we can train on.
        if not ensemble:
            train_index_, y_train = subset_indices(
                driams_dataset.y,
                train_index,
                args.species
            )

        # Ensemble mode: just use the regular train index. The reason
        # for choosing a different variable name is because I do not
        # want to overwrite anything here.
        else:
            train_index_ = train_index
            y_train = driams_dataset.y.iloc[train_index]

        y_train = driams_dataset.to_numpy(args.antibiotic, y=y_train)

        X_train = X[train_index_]
        X_test = X[test_index_]

        n_folds = 5

        # Fit the classifier and start calculating some summary metrics.
        # All of this is wrapped in cross-validation based on the grid
        # defined above.
        lr = LogisticRegression(solver='saga', max_iter=500)

        pipeline = Pipeline(
            steps=[
                ('scaler', None),
                ('lr', lr),
            ]
        )

        param_grid = [
            {
                'scaler': ['passthrough', StandardScaler()],
                'lr__C': 10.0 ** np.arange(-3, 4),  # 10^{-3}..10^{3}
                'lr__penalty': ['l1', 'l2'],
            },
            {
                'scaler': ['passthrough', StandardScaler()],
                'lr__penalty': ['none'],
            }
        ]

        grid_search = GridSearchCV(
                        pipeline,
                        param_grid=param_grid,
                        cv=n_folds,
                        scoring='roc_auc',
                        n_jobs=-1,
        )

        logging.info('Starting grid search')

        # Ignore these warnings only for the grid search process. The
        # reason is that some of the jobs will inevitably *fail* to
        # converge because of bad `C` values. We are not interested in
        # them anyway.
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=ConvergenceWarning)
            warnings.filterwarnings('ignore', category=UserWarning)

            with joblib.parallel_backend('threading', -1):
                grid_search.fit(X_train, y_train)

        y_pred = grid_search.predict(X_test)
        y_score = grid_search.predict_proba(X_test)

        accuracy = accuracy_score(y_pred, y_test)
        auprc = average_precision_score(y_test, y_score[:, 1])
        auroc = roc_auc_score(y_test, y_score[:, 1])

        # Replace information about the standard scaler prior to writing out
        # the `best_params_` grid. The reason for this is that we cannot and
        # probably do not want to serialise the scaler class. We only need
        # to know *if* a scaler has been employed.
        if 'scaler' in grid_search.best_params_:
            scaler = grid_search.best_params_['scaler']
            if scaler != 'passthrough':
                grid_search.best_params_['scaler'] = type(scaler).__name__

        # Prepare the output dictionary containing all information to
        # reproduce the experiment.

        output = {
            'site': site,
            'species': args.species,
            'seed': args.seed,
            'antibiotic': args.antibiotic,
            'best_params': grid_search.best_params_,
            'years': years,
            'y_score': y_score.tolist(),
            'y_pred': y_pred.tolist(),
            'y_test': y_test.tolist(),
            'accuracy': accuracy,
            'auprc': auprc,
            'auroc': auroc,
        }

        # Add fingerprint information about the metadata files to make sure
        # that the experiment is reproducible.
        output['metadata_versions'] = metadata_fingerprints

        output_filename = generate_output_filename(
            args.output,
            output,
            suffix='ensemble' if ensemble else 'single'
        )

        # Only write if we either are running in `force` mode, or the
        # file does not yet exist.
        if not os.path.exists(output_filename) or args.force:
            logging.info(f'Saving {os.path.basename(output_filename)}')

            with open(output_filename, 'w') as f:
                json.dump(output, f, indent=4)
        else:
            logging.warning(
                f'Skipping {output_filename} because it already exists.'
            )
