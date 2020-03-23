"""
Plotting script to create

Figure 2 - barplots: compare prediction from spectra vs. from species
information 

MALDI-TOF spectra based AMR prediction using an ensemble of all species
"""

import os
import json
import argparse

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.metrics import roc_curve, roc_auc_score, precision_recall_curve, average_precision_score
# from maldi_learn.metrics import very_major_error_score, major_error_score, vme_curve, vme_auc_score

def plot_figure2(args):

    PATH_fig2 = '../results/fig2_baseline/'

    # --------------
    # create dataframe giving an overview of all files in path
    # --------------
    file_list = []
    for (_, _, filenames) in os.walk(PATH_fig2):
        [file_list.append(f) for f in filenames if '.json' in f]
        break

    content = pd.DataFrame(columns=['filename',
                                    'species',
                                    'antibiotic',
                                    'site',
                                    'seed',
                                    ])

    for filename in file_list:
        with open(PATH_fig2 + filename) as f:
            data = json.load(f)
            content = content.append(
                pd.DataFrame({
                    'filename': [filename],
                    'species': [data['species']],
                    'antibiotic': [data['antibiotic']],
                    'site': [data['site']],
                    'seed': [data['seed']],
                    }),
                ignore_index=True,
                )

    # TODO give option to take antibiotic list from args.antibiotics
    # or take everything otherwise

    # ------------
    # for each antibiotic, get avg metrics for 'all' and 'all (w/o spectra)'
    # ------------

    values = pd.DataFrame(columns=['antibiotic',
                                   'auroc_all',
                                   'auroc_all_wo_spectra',
                                   ])

    # add lines for each antibiotic
    for antibiotic in set(content['antibiotic']):
        print(antibiotic)
        content_ab = content.query('antibiotic==@antibiotic')
        assert content_ab.shape == (20, 5)

        content_spectra = content_ab.query("species=='all'")
        content_wo_spectra = content_ab.query("species=='all (w/o spectra)'")

        # 'all': extract y_test and y_score from json files
        aurocs = []
        class_ratios = []

        for filename in content_spectra['filename'].values:
            with open(PATH_fig2 + filename) as f:
                data = json.load(f)
                aurocs.append(roc_auc_score(data['y_test'],
                              [sc[1] for sc in data['y_score']]))
                assert np.all([x in [0, 1] for x in data['y_test']])
                class_ratios.append(float(sum(data['y_test']))/len(data['y_test'
                                                                        ]))
        class_ratio = '{:0.2f}'.format(np.mean(class_ratios))
        auroc_mean_all = round(np.mean(aurocs), 3)
        auroc_std_all = round(np.std(aurocs), 3)

        # 'all (w/o spectra)': extract y_test and y_score from json files
        aurocs = []

        for filename in content_wo_spectra['filename'].values:
            with open(PATH_fig2 + filename) as f:
                data = json.load(f)
                aurocs.append(roc_auc_score(data['y_test'],
                              [sc[1] for sc in data['y_score']]))

        auroc_mean_all_wo_spectra = round(np.mean(aurocs), 3)
        auroc_std_all_wo_spectra = round(np.std(aurocs), 3)

        values = values.append(
            pd.DataFrame({
                'antibiotic': [antibiotic],
                'label': [f'{antibiotic} [{class_ratio}]'],
                'auroc_all': [auroc_mean_all],
                'auroc_all_wo_spectra': [auroc_mean_all_wo_spectra],
                'auroc_std_all': [auroc_std_all],
                'auroc_std_all_wo_spectra': [auroc_std_all_wo_spectra],
                }),
            ignore_index=True,
            )

    # correct Cotrimoxazole spelling
    values = values.replace({'Cotrimoxazol': 'Cotrimoxazole'})

    # -------------
    # plot barplot
    # -------------

    values = values.sort_values(by=['auroc_all'], ascending=False)
    n_ab = len(values)

    sns.set(style="whitegrid",
            font_scale=2)
    fig, ax = plt.subplots(figsize=(22, 15))

    sns.barplot(x="label", y="auroc_all",
                ax=ax, data=values, color=sns.color_palette()[0])
    sns.barplot(x="label", y="auroc_all_wo_spectra",
                ax=ax, data=values, color='firebrick')

    ax.errorbar(list(range(0, n_ab)),
                values['auroc_all'].values,
                yerr=values['auroc_std_all'].values,
                fmt='o',
                color='black')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=90)
    plt.ylabel('AUROC')
    plt.xlabel('')
    plt.ylim(0.5, 1.05)
    plt.xlim(0-0.5, n_ab-0.5)

    # TODO include class ratios
    # TODO include p-values

    plt.tight_layout()
    plt.savefig('./test.png')


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--antibiotic',
                        type=str,
                        default='Ciprofloxacin')
    args = parser.parse_args()

    plot_figure2(args)
