import numpy as np
import pandas as pd

import logging
import itertools

from sklearn.base import BaseEstimator, ClassifierMixin

class GaussianRBM(BaseEstimator, ClassifierMixin):
    pass

class ConditionalRBM(BaseEstimator, ClassifierMixin):
    pass

class ConditionalFactoredRBM(BaseEstimator, ClassifierMixin):
    pass

def sigmoid(eta):
    return 1. / (1. + np.exp(-eta))

def identity(x):
    return x

def bernoulli(p):
    return np.random.rand(*p.shape) < p

def softmax(w):
    n = w.shape[0]
    w = np.array(w)
    maxes = np.amax(w, axis=1)
    maxes = maxes.reshape(n, 1)
    e = np.exp(w - maxes)
    return e / np.sum(e, axis=1).reshape(n, 1)

class RBM(BaseEstimator, ClassifierMixin):
    def __init__(self, T=1, n_hidden=100, hidden_type='binary', scale = 0.001, rating_levels=[1,2,3,4,5],
                 momentum=0., lam=0.01, batch_size=200, learning_rate=0.2):
        self.T = T
        self.n_hidden = n_hidden
        self.hidden_type = hidden_type
        self.scale = scale
        self.rating_levels = pd.Index(rating_levels)
        self.momentum = momentum
        self.lam = lam
        self.batch_size = batch_size
        self.learning_rate = learning_rate

        self.h_bias_ = np.array(None)
        self.v_bias_ = np.array(None)
        self.weights_ = np.array(None)
        self._hidden = None

    def fit(self, items, ratings):
        self._item_index = items.index

        self.h_bias_ = 2 * self.scale * np.random.randn(self.n_hidden)
        self.v_bias_ = self.scale * np.random.randn(items.index.shape[0], self.n_rating_levels)
        self.weights_ = self.scale * np.random.randn(self.n_rating_levels, self.n_hidden, self.n_visible)

        self._grad_hid = np.zeros_like(self.h_bias_)
        self._grad_vis = np.zeros_like(self.v_bias_)
        self._grad_weights = np.zeros_like(self.weights_)
        
        ## self._hidden = self.hidden_type=='binary' and sigmoid or identity

        ratings_map = ratings.groupby('user_id').groups
        for uid in ratings_map:
            ratings_uid = ratings.loc[ratings_map[uid],'stars']
            bids = ratings.loc[ratings_map[uid],'business_id']

            n_ratings = ratings_uid.shape[0]
            _, bid_indices = self._item_index.reindex(bids)
            ratings_ = np.zeros((n_ratings, self.n_rating_levels))
            ratings_[np.arange(n_ratings), self.rating_levels.reindex(ratings_uid)[1]] = 1.

            gradients = self.calculate_gradients(ratings_, bid_indices)
            self.apply_gradients(*gradients, learning_rate=self.learning_rate, item_indices=bid_indices)
        
    @property
    def n_visible(self): return self.v_bias_.shape[0]

    @property
    def n_rating_levels(self): return self.rating_levels.shape[0]

    def iter_passes(self, visible, item_indices=None):
        if item_indices is None:
            item_indices = slice(None, None)
        while True:
            ## weights: ratings x nhidden x nvisible
            ## visible: nvisible x ratings
            ## h_bias : nhidden
            hidden = bernoulli(sigmoid(np.tensordot(self.weights_[:,:,item_indices], visible, axes=([0,2],[1,0])).T + self.h_bias_))
            yield visible, hidden
            ## hidden: nhidden
            ## weights: ratings x nhidden x nvisible
            ## v_bias: nvisible x ratings
            visible = softmax(np.tensordot(hidden, self.weights_[:,:,item_indices], axes=(0, 1)).T + self.v_bias_[item_indices,:])

    def calculate_gradients(self, visible, item_indices=None):
        passes = self.iter_passes(visible, item_indices)
        
        v0, h0 = passes.next()
        v1, h1 = itertools.islice(passes, self.T, self.T+1).next()

        ## h: nhidden
        ## v: nvisible * nratings
        ## w: ratings x nhidden x nvisible
        nhidden = h0.shape[0]
        nvisible, nratings = v0.shape
        gw = (np.rollaxis(np.tensordot(v0.T, h0, axes=0), 2, 1) - np.rollaxis(np.tensordot(v1.T, h0, axes=0), 2, 1))
        gv = (v0 - v1)
        gh = (h0 - h1)

        return gw, gv, gh

    def apply_gradients(self, weights, visible, hidden, learning_rate, item_indices=None):
        if item_indices is None:
            item_indices = slice(None, None)

        self._grad_vis *= self.momentum
        self._grad_vis[item_indices,:] -=  learning_rate * visible
        self.v_bias_ += self._grad_vis

        self._grad_hid = self.momentum * self._grad_hid - learning_rate * hidden
        self.h_bias_ += self._grad_hid

        self._grad_weights *= self.momentum
        self._grad_weights[:,:,item_indices] -= learning_rate * weights
        self.weights_ += self._grad_weights

    def predict(self, connections, to_predict, method='exp'):
        '''
        Make predictions from fitted model

        Parameters
        ----------
        connections : vector of user-item pairs of connections

        to_predict : vector of user-item pairs to predict

        method : method, mf = mean-field
                         map = argmax unnormalized score
                         exp = expectation over normalized scores

        Returns
        -------
        y : predicted ratings
        '''
        if method != 'exp':
            raise NotImplementedError

        n_pred = to_predict.shape[0]

        ## i = n_visible
        ## q = n_visible
        ## l = n_ratings
        ## k = n_ratings
        ## j = n_hidden

        ## TODO: fix this entire function. it is so ugly
        
        user_map = connections.groupby('user_id').groups

        pi = np.zeros((n_pred, self.n_rating_levels))
        gammas = np.zeros((n_pred, self.n_rating_levels))

        def inner(uid, q_index, k_index, j):
            _, bid_indices = self._item_index.reindex(user_map[uid])
            W_l = self.weights_[:,j,bid_indices]
            W_k = self.weights_[k_index,j,q_index]
            
            s = self.h_bias_[j] + W_l + W_k
            return 1 + np.exp(np.sum(s))
            
        for qi, (_, (q, uid)) in enumerate(to_predict.loc[:,['business_id', 'user_id']].iterrows()):
            q_index = self._item_index.get_loc(q)
            for k in self.rating_levels:
                k_index = self.rating_levels.get_loc(k)
                pi[qi, k_index] = np.prod(map(lambda j: inner(uid, q_index, k_index, j), range(self.n_hidden)))
                gammas[qi, k_index] = np.exp(np.where(q in user_map[uid], 1, 0) *
                                       self.v_bias_[q_index, k_index])
        
        probs = gammas * pi                 # n_pred(q) x n_ratings(k)

        ## normalize and compute expectation
        probs /= np.sum(probs, axis=1).reshape(n_pred, 1)
        Y = np.sum(self.rating_levels * probs, axis=1)

        return Y
