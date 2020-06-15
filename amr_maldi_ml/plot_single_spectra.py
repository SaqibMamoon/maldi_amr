
"""
Plot a single raw MALDI-TOF mass spectra.
"""
import glob
import os

import pandas as pd
from dotenv import load_dotenv
import seaborn as sns

from maldi_learn.driams import load_driams_dataset
from maldi_learn.driams import DRIAMSDatasetExplorer
from maldi_learn.driams import DRIAMSLabelEncoder

load_dotenv()
DRIAMS_ROOT = os.getenv('DRIAMS_ROOT')

pair = [
    ('Escherichia coli', 'Ciprofloxacin'),
			  ]

def load_single_raw_spectrum(pair, year, site):

    driams = load_driams_dataset(
    DRIAMS_ROOT,
    site,
    year,
    pair[0],
    pair[1],
    encoder=DRIAMSLabelEncoder(),
    handle_missing_resistance_measurements='remove_if_any_missing',
    spectra_type='raw',
    )

    # return first spectrum from list
    return driams.X[0]



if __name__=='__main__':
    
    raw_spectrum = load_single_raw_spectrum(pair, '2018', 'DRIAMS-A')
    print(raw_spectrum)

