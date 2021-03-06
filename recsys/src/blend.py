import pandas as pd
import numpy as np
import scipy as sp

import os

from sklearn.linear_model import Lars, BayesianRidge, Ridge
from sklearn.ensemble import GradientBoostingRegressor

if __name__ == '__main__':
    blend_inputs = [('svdpp25', 'svdpp_submission_i25_f100.csv', 'svdpp_fitted_i25_f100.csv'),
                    ('factor25', 'factor_submission_i25_f100.csv', 'factor_fitted_i25_f100.csv'),
                    ('nsvd25', 'nsvd_submission_i25_f100.csv', 'nsvd_fitted_i25_f100.csv'),
                    ('nsvd50', 'nsvd_submission_i50_f100.csv', 'nsvd_fitted_i50_f100.csv'),
                    ('int10', 'integrated_submission_i10_f100.csv', 'integrated_fitted_i10_f100.csv'),
                    ('int25', 'integrated_submission_i25_f100.csv', 'integrated_fitted_i25_f100.csv'),
                    ('n10', 'neighbors_submission_i10.csv', 'neighbors_fitted_i10.csv'),
                    ('n25', 'neighbors_submission_i25.csv', 'neighbors_fitted_i25.csv'),
                    ('tn25', 'timeneighbors_submission_i25.csv', 'timeneighbors_fitted_i25.csv'),
                    ('locn10', 'locneighbors_submission_i10.csv', 'locneighbors_fitted_i10.csv'),
                    ('locint10', 'locintegrated_submission_i10.csv', 'locintegrated_fitted_i10.csv'),
                    # ('rbm100', 'rbm_submission_e50_h100.csv', 'rbm_fitted_e50_h100.csv'),
                    # ('rbm50', 'rbm_submission_e50_h50.csv', 'rbm_fitted_e50_h50.csv'),
                    # ('ppru', 'ppr_submission_user.csv', 'ppr_fitted_user.csv'),
                    # ('pprg', 'ppr_submission_global.csv', 'ppr_fitted_global.csv'),
                    ]

    fitted = pd.DataFrame(index=review_data.index)
    submission = pd.DataFrame(index=review_data_final.index)
    for name, sub_name, fit_name in blend_inputs:
        f_df = pd.read_csv(os.path.join('..', fit_name))
        f_df.index = review_data.index
        fitted[name] = f_df['stars']
        s_df = pd.read_csv(os.path.join('..', sub_name))
        s_df.index = review_data_final.index
        submission[name] = s_df['stars']

    gbr = GradientBoostingRegressor(max_depth=3,verbose=2)
    gbr.fit(fitted, review_data['stars'])
    pred = gbr.predict(submission)
    pd.DataFrame({'review_id' : submission.index, 'stars' : np.maximum(1, np.minimum(5, pred))}).to_csv('../gbr_submission.csv', index=False)

    lar = Lars(fit_intercept=True, verbose=2, normalize=True, fit_path=True)
    lar.fit(fitted, review_data['stars'])
    pred = lar.predict(submission)
    pd.DataFrame({'review_id' : submission.index, 'stars' : np.maximum(1, np.minimum(5, pred))}).to_csv('../lar_submission.csv', index=False)

    ridge = Ridge()
    ridge.fit(fitted, review_data['stars'])
    pred = ridge.predict(submission)
    pd.DataFrame({'review_id' : submission.index, 'stars' : np.maximum(1, np.minimum(5, pred))}).to_csv('../ridge_submission.csv', index=False)
    
    ## TODO: blend based on size of rating neighborhood
