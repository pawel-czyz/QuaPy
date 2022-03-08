import numpy as np
import quapy as qp
from Ordinal.evaluation import nmd
from Ordinal.utils import load_samples_pkl
from quapy.data import LabelledCollection
import pickle
import os
from os.path import join
from tqdm import tqdm


def partition_by_drift(split, training_prevalence):
    assert split in ['dev', 'test'], 'invalid split name'
    total=1000 if split=='dev' else 5000
    drifts = []
    for sample in tqdm(load_samples_pkl(join(datapath, domain, 'app', f'{split}_samples')), total=total):
        drifts.append(nmd(training_prevalence, sample.prevalence()))
    drifts = np.asarray(drifts)
    order = np.argsort(drifts)
    nD = len(order)
    low_drift, mid_drift, high_drift = order[:nD // 3], order[nD // 3:2 * nD // 3], order[2 * nD // 3:]
    np.save(join(datapath, domain, 'app', f'lowdrift.{split}.id.npy'), low_drift)
    np.save(join(datapath, domain, 'app', f'middrift.{split}.id.npy'), mid_drift)
    np.save(join(datapath, domain, 'app', f'highdrift.{split}.id.npy'), high_drift)
    lows = drifts[low_drift]
    mids = drifts[mid_drift]
    highs = drifts[high_drift]
    print(f'low drift: interval [{lows.min():.4f}, {lows.max():.4f}] mean: {lows.mean():.4f}')
    print(f'mid drift: interval [{mids.min():.4f}, {mids.max():.4f}] mean: {mids.mean():.4f}')
    print(f'high drift: interval [{highs.min():.4f}, {highs.max():.4f}] mean: {highs.mean():.4f}')


domain = 'Books-tfidf'
datapath = './data'

training = pickle.load(open(join(datapath,domain,'training_data.pkl'), 'rb'))

partition_by_drift('dev', training.prevalence())
partition_by_drift('test', training.prevalence())

