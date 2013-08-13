import numpy as np
import pandas as pd
import scipy as sp

from sklearn.base import BaseEstimator, RegressorMixin

import logging
import time

class KorenNgbr(BaseEstimator, RegressorMixin):
    '''Nearest-Neighbors algorithm from [Koren2008]

    Parameters
    ----------
    gamma: learning rate

    lam: normalization constant for biases and weights

    n_iter: number of training epochs

    k: neighborhood size limit (not used)

    shrinkage: shrinkage constant for item similarities (not used)

    Attributes
    ----------
    `mu_` : global mean (float)

    `b_user_` : vect of user biases

    `b_item_` : vect of item biases

    `w_ij_` : matrix of offset weights

    `c_` : matrix of implicit item effects (not used)

    Notes
    -----
    See Factorization Meets the Neighborhood: a Multifaceted
    Collaborative Filtering Model (Koren, 2008) for a
    description of algorithm and parameters (Sec 3)
    '''
    
    def __init__(self, gamma=0.005, lam=0.002, n_iter=1,
                 k=500, shrinkage=50):
        self.gamma = gamma
        self.lam = lam
        self.n_iter = n_iter

        ## not implemented
        self.k = k
        self.shrinkage = shrinkage

        ## model parameters
        self.mu_ = None                   # global mean
        self.b_user_ = None               # user bias
        self.b_item_ = None               # item bias
        self.w_ij_ = None                 # baseline offsets
        self.c_ = None

    def fit(self, X, y=None):
        '''
        Fit model.

        Parameters
        ----------
        X : array of business_data, review_data, user_data, checkin_data

        y : not used

        Returns
        -------
        self : instance of self
        '''
        (bus_data, review_data, user_data, checkin_data) = X

        self.b_user_ = pd.Series(0, index=user_data.index.union(review_data['user_id']).unique())
        self.b_item_ = pd.Series(0, index=bus_data.index)
        self._w_ij_index = bus_data.index
        self.w_ij_ = sp.sparse.lil_matrix((bus_data.index.shape[0], bus_data.index.shape[0]))
        self.mu_ = review_data['stars'].mean()

        l = self.lam
        g = self.gamma
        mu = self.mu_

        t1 = time.clock()
        print 'generating user prediction functions'

        def pred_clos(df):
            uid = df.ix[0, 'user_id']
            R_items = df.loc[:,'business_id']
            R_user_bias = mu + np.add(self.b_user_.get(uid, default=0), self.b_item_.loc[R_items])
            offset = np.subtract(df.loc[:,'stars'], R_user_bias)
            R = df.shape[0] ** -0.5
            def f(bid):
                xi = self._w_ij_index.get_loc(bid)
                yi = self._w_ij_index.reindex(R_items)[1]
                return mu+self.b_user_.get(uid, default=0)+self.b_item_.loc[bid]+R*self.w_ij_[xi,yi].dot(offset)
            return f
        self._preds = review_data.groupby('user_id').agg(pred_clos)

        t2 = time.clock()
        print 'finished precomputation in %dm' % ((t2 - t1) / 60.)
        print 'starting training'

        R = review_data.groupby('user_id').groups
        ii = 1
        for _ in xrange(self.n_iter):
            for i, (uid, bid, stars) in review_data[['user_id', 'business_id', 'stars']].iterrows():
                if ii % 1000 == 0: print "on review %d" % ii
                ii += 1
                err = stars - self._preds.loc[uid, 0](bid)
                self.b_user_.loc[uid] += g * (err - l * self.b_user_.loc[uid])
                self.b_item_.loc[bid] += g * (err - l * self.b_item_.loc[bid])
                xi = self._w_ij_index.get_loc(bid)
                yi = self._w_ij_index.reindex(review_data.ix[R[uid],'business_id'])[1]
                base_rat = mu + self.b_user_.loc[uid] + self.b_item_.loc[review_data.ix[R[uid],'business_id']]
                self.w_ij_[xi,yi] = self.w_ij_[xi,yi] + g * np.subtract(len(R[uid]) ** -0.5 * err * np.subtract(review_data.ix[R[uid],'stars'], base_rat), l * self.w_ij_[xi,yi].todense())

        t3 = time.clock()
        print 'finished training in %dm' % ((t3 - t2) / 60.)
        
        return self

    def predict(self, X):
        '''
        Make prediction from fitted model.

        Parameters
        ----------
        X : array of business_data, review_data, user_data, checkin_data

        Returns
        -------
        y : vector of predicted ratings
        '''
        return X[1].apply(lambda row: self._preds.ix[row['user_id'],0](row['business_id']), axis=1)

class KorenIntegrated(BaseEstimator, RegressorMixin):
    '''Integrated model from [Koren2008]

    Parameters
    ----------
    gam1: bias learning rate

    gam2: latent factor learning rate

    gam3: weight learning rate

    lam6: bias regularization constant

    lam7: latent factor regularization constant

    lam8: weight regularization constant

    n_iter: number of training epochs

    n_factors: number of latent factors to use

    k: neighborhood size limit (not used)

    shrinkage: shrinkage constant for item similarities (not used)

    Attributes
    ----------
    `mu_` : global mean (float)

    `b_user_` : dict of user biases

    `b_item_` : dict of item biases

    `w_ij_` : dict of offset weights

    `p_` : matrix of user factors

    `q_` : matrix of item factors

    `y_` : implicit user factors

    `c_` : matrix of implicit item effects

    Notes
    -----
    See Factorization Meets the Neighborhood: a Multifaceted
    Collaborative Filtering Model (Koren, 2008) for a
    description of algorithm and parameters (Sec 5)
    '''
    
    def __init__(self, gam1=0.007, gam2=0.007, gam3=0.001,
                 lam6=0.005, lam7=0.015, lam8=0.015,
                 n_iter=1, n_factors=50,
                 k=300, shrinkage=50):
        self.gam1 = gam1
        self.gam2 = gam2
        self.gam3 = gam3
        self.lam6 = lam6
        self.lam7 = lam7
        self.lam8 = lam8
        self.n_iter = n_iter
        self.n_factors = n_factors

        ## not implemented
        self.k = k
        self.shrinkage = shrinkage

        ## model parameters
        self.mu_ = None                   # global mean
        self.b_user_ = None               # user bias
        self.b_item_ = None               # item bias
        self.w_ij_ = None                 # baseline offsets
        self.p_ = None
        self.q_ = None
        self.y_ = None
        self.c_ = None

    def fit(self, X, y=None):
        '''
        Fit model.

        Parameters
        ----------
        X : array of business_data, review_data, review_data_implicit, user_data, checkin_data

        y : not used

        Returns
        -------
        self : instance of self
        '''
        (bus_data, review_data, review_data_implicit, user_data, checkin_data) = X

        all_user_index = user_data.index \
          .union(pd.Index(review_data['user_id'].unique())) \
          .union(pd.Index(review_data_implicit['user_id'].unique())) \
          .unique()
        self.b_user_ = pd.Series(0, index=all_user_index)
        self.b_item_ = pd.Series(0, index=bus_data.index)
        self._w_ij_index = bus_data.index
        self.w_ij_ = sp.sparse.lil_matrix((bus_data.shape[0], bus_data.shape[0]))
        self.c_ = sp.sparse.lil_matrix((bus_data.shape[0], bus_data.shape[0]))
        self.p_ = pd.DataFrame(0, index=all_user_index, columns=range(self.n_factors))
        self.q_ = pd.DataFrame(0, index=bus_data.index, columns=range(self.n_factors))
        self.y_ = pd.DataFrame(0, index=bus_data.index, columns=range(self.n_factors))
        self.mu_ = review_data['stars'].mean()

        self._review_data = review_data
        self._review_data_implicit = review_data_implicit
        self._review_map = review_data.groupby('user_id').groups
        self._review_implicit_map = review_data_implicit.groupby('user_id').groups

        print 'starting training'
        t2 = time.clock()

        ii = 1
        for _ in xrange(self.n_iter):
            for i, (uid, bid, stars) in review_data[['user_id', 'business_id', 'stars']].iterrows():
                if ii % 1000 == 0: print "on review %d" % ii
                ii += 1
                err = stars - self._pred(uid, bid)
                invroot_R_mag = len(self._review_map[uid]) ** -0.5
                invroot_N_mag = len(self._review_implicit_map[uid]) ** -0.5
                ## general
                self.b_user_.loc[uid] += self.gam1 * (err - self.lam6 * self.b_user_.loc[uid])
                self.b_item_.loc[bid] += self.gam1 * (err - self.lam6 * self.b_item_.loc[bid])
                ## latent
                N_items = self._review_data_implicit.loc[self._review_implicit_map[uid],'business_id']
                self.q_.loc[bid,:] += self.gam2 * (err * (self.p_.loc[uid,:] +
                                                          invroot_N_mag * self.y_.loc[N_items].sum(axis=0))
                                                   - self.lam7 * self.q_.loc[bid,:])
                self.p_.loc[uid,:] += self.gam2 * (err * self.q_.loc[bid,:] - self.lam7 * self.p_.loc[uid,:])
                self.y_.loc[bid,:] += self.gam2 * (err * invroot_N_mag * self.q_.loc[bid,:] - self.lam7 * self.y_.loc[bid,:])
                ## neighborhood
                xi = self._w_ij_index.get_loc(bid)
                w_yi = self._w_ij_index.reindex(review_data.loc[self._review_map[uid],'business_id'])[1]
                c_yi = self._w_ij_index.reindex(review_data_implicit.loc[self._review_implicit_map[uid],'business_id'])[1]
                base_rat = self.mu_ + self.b_user_.loc[uid] + self.b_item_.loc[review_data.loc[self._review_map[uid],'business_id']]
                self.w_ij_[xi,w_yi] = self.w_ij_[xi,w_yi] + self.gam3 * np.subtract(invroot_R_mag * err * \
                    np.subtract(review_data.loc[self._review_map[uid],'stars'], base_rat), self.lam8 * self.w_ij_[xi,w_yi].todense())
                self.c_[xi,c_yi] = self.c_[xi,c_yi] + self.gam3 * np.subtract(invroot_N_mag * err, self.lam8 * self.c_[xi,c_yi].todense())

        t3 = time.clock()
        print 'finished training in %dm' % ((t3 - t2) / 60.)
        
        return self

    def predict(self, X):
        '''
        Make prediction from fitted model.

        Parameters
        ----------
        X : review_data format dataframe

        Returns
        -------
        y : vector of predicted ratings
        '''
        return X.apply(lambda row: self._pred(row['user_id'], row['business_id']), axis=1)

    def _pred(self, uid, bid):
        '''
        Make prediction from fitted model.

        Parameters
        ----------
        uid : `user_id`

        bid : `business_id`

        Returns
        -------
        y : predicted rating
        '''
        if uid in self._review_map:
            review_data_user = self._review_data.loc[self._review_map[uid]]
            review_data_implicit_user = self._review_data_implicit.loc[self._review_implicit_map[uid]]
            
            R_items = review_data_user.loc[:,'business_id']
            N_items = review_data_implicit_user.loc[:,'business_id']
            
            b_u = self.mu_ + np.add(self.b_user_.loc[uid], self.b_item_.loc[R_items])
            
            invroot_R_mag = review_data_user.shape[0] ** -0.5
            invroot_N_mag = review_data_implicit_user.shape[0] ** -0.5
            
            xi = self._w_ij_index.get_loc(bid)
            w_yi = self._w_ij_index.reindex(R_items)[1]
            c_yi = self._w_ij_index.reindex(N_items)[1]
            
            general = self.mu_+self.b_user_.loc[uid]+self.b_item_.loc[bid]
            latent = np.dot(self.q_.loc[bid,:], np.add(self.p_.loc[uid,:], invroot_N_mag * self.y_.loc[N_items].sum(axis=0)))
            neighborhood = invroot_R_mag*self.w_ij_[xi,w_yi].dot(np.subtract(review_data_user.loc[:,'stars'], b_u))
            neighborhood_implicit = invroot_N_mag * self.w_ij_[xi,c_yi].sum()
            
            return general + latent + neighborhood + neighborhood_implicit
        else:
            review_data_implicit_user = self._review_data_implicit.loc[self._review_implicit_map[uid]]
            
            N_items = review_data_implicit_user.loc[:,'business_id']
            
            invroot_N_mag = review_data_implicit_user.shape[0] ** -0.5
            
            xi = self._w_ij_index.get_loc(bid)
            c_yi = self._w_ij_index.reindex(N_items)[1]
            
            general = self.mu_+self.b_item_.loc[bid]
            latent = np.dot(self.q_.loc[bid,:], np.add(self.p_.loc[uid,:], invroot_N_mag * self.y_.loc[N_items].sum(axis=0)))
            neighborhood_implicit = invroot_N_mag * self.w_ij_[xi,c_yi].sum()
            
            return general + latent + neighborhood_implicit
