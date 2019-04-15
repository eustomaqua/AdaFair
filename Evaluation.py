import random
from collections import defaultdict
from multiprocessing import Process, Lock
import pickle
import os
import matplotlib
import numpy
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import ShuffleSplit
from sklearn.naive_bayes import GaussianNB

matplotlib.use('Agg')
import sys
import pandas as pd

from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.ensemble import AdaBoostClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier

from AccumFairAdaCost import AccumFairAdaCost

sys.path.insert(0, 'DataPreprocessing')
sys.path.insert(0, 'equalized_odds_and_calibration-master')

from eq_odds import Model
from call_eq_odds import Model as calibModel
import funcs_disp_mist as fdm

import time
from sklearn.model_selection import StratifiedKFold
from AdaCost import AdaCostClassifier
from FairAdaCost import FairAdaCost

from load_dutch_data import load_dutch_data
# from load_german import load_german
from load_compas_data import load_compas
from load_adult import load_adult
from load_kdd import load_kdd

from load_bank import load_bank
from my_useful_functions import calculate_performance, plot_my_results
import utils as ut


class serialazible_list(object):
    def __init__(self):
        self.performance = []


def create_temp_files(dataset, suffixes):
    for suffix in suffixes:
        outfile = open(dataset + suffix, 'wb')
        pickle.dump(serialazible_list(), outfile)
        outfile.close()

    if not os.path.exists("Images/"):
        os.makedirs("Images/")


def delete_temp_files(dataset, suffixes):
    for suffix in suffixes:
        os.remove(dataset + suffix)


def predict(clf, X_test, y_test, sa_index, p_Group):
    y_pred_probs = clf.predict_proba(X_test)[:, 1]
    y_pred_labels = clf.predict(X_test)
    return calculate_performance(X_test, y_test, y_pred_labels, y_pred_probs, sa_index, p_Group)


def run_eval(dataset, iterations):
    # suffixes = ['adaboost', 'Sin.1', 'Sin.2', 'Cumul.1', 'Cumul.2', 'zafar', 'Hardt', 'Pleiss']
    # suffixes = ['adaboost', 'Cumul.1', 'Cumul.2', 'zafar', 'Hardt', 'Pleiss']
    # suffixes = ['adaboost', 'Cumul.1', 'Cumul.2', 'zafar', 'Hardt']
    suffixes = ['Hardt et al.','Zafar et al.', 'Adaboost', 'AFB' ]
    create_temp_files(dataset, suffixes)

    if dataset == "compass-gender":
        X, y, sa_index, p_Group, x_control = load_compas("sex")
    elif dataset == "compass-race":
        X, y, sa_index, p_Group, x_control = load_compas("race")
    elif dataset == "adult-gender":
        X, y, sa_index, p_Group, x_control = load_adult("sex")
    elif dataset == "adult-race":
        X, y, sa_index, p_Group, x_control = load_adult("race")
    elif dataset == "dutch":
        X, y, sa_index, p_Group, x_control = load_dutch_data()
    elif dataset == "bank":
        X, y, sa_index, p_Group, x_control = load_bank()
    elif dataset == "kdd":
        X, y, sa_index, p_Group, x_control = load_kdd()
        # suffixes = ['adaboost', 'Cumul.1', 'Cumul.2', 'Hardt', 'Pleiss']
        # suffixes = ['adaboost', 'Cumul.1', 'Cumul.2', 'Hardt']
        suffixes = ['Adaboost', 'Accum.FairBoosting', 'Hardt et al.']
        suffixes = ['Hardt et al.','Adaboost', 'AFB']

    else:
        exit(1)
    create_temp_files(dataset, suffixes)

    # init parameters for zafar method (default settings)
    tau = 3.0
    mu = 1.2
    cons_type = 4
    sensitive_attrs = x_control.keys()
    loss_function = "logreg"
    EPS = 1e-6
    sensitive_attrs_to_cov_thresh = {sensitive_attrs[0]: {0: {0: 0, 1: 0}, 1: {0: 0, 1: 0}, 2: {0: 0, 1: 0}}}
    cons_params = {"cons_type": cons_type, "tau": tau, "mu": mu,
                   "sensitive_attrs_to_cov_thresh": sensitive_attrs_to_cov_thresh}

    threads = []
    mutex = []
    for lock in range(0, 8):
        mutex.append(Lock())

    random.seed(12345)

    for iter in range(0, iterations):
        start = time.time()

        # for zafar's approach need to specify test and train indeces from the beginning
        temp_shuffle_array = [i for i in range(0, len(X))]
        random.shuffle(temp_shuffle_array)
        train1 = temp_shuffle_array[: int(len(X)/2)]
        test1  = temp_shuffle_array[int(len(X)/2): int(len(X)/2) + int(len(X)/4)]
        valid1 = temp_shuffle_array[int(len(X)/2) + int(len(X)/4):]

        train2 = temp_shuffle_array[int(len(X)/2):]
        test2  = temp_shuffle_array[:int(len(X)/2) - int(len(X)/4)]
        valid2 = temp_shuffle_array[int(len(X)/2) - int(len(X)/4):int(len(X)/2)]

        for train_index, test_index, valid_index in [[train1, test1, valid1],[train2, test2, valid2]]:

            X_train, X_test, X_valid = X[train_index], X[test_index], X[valid_index]
            y_train, y_test, y_valid = y[train_index], y[test_index], y[valid_index]

            for proc in range(0, 4):
                if dataset == "kdd" and proc == 1:
                    continue

                if proc > 1:
                    threads.append(Process(target=train_classifier, args=( X_train, X_test, y_train, y_test, sa_index, p_Group, dataset + suffixes[proc], mutex[proc],proc, 200, 1)))

                elif proc == 1:
                    temp_x_control_train = defaultdict(list)
                    temp_x_control_test = defaultdict(list)

                    temp_x_control_train[sensitive_attrs[0]] = x_control[sensitive_attrs[0]][train_index]
                    temp_x_control_test[sensitive_attrs[0]] = x_control[sensitive_attrs[0]][test_index]

                    x_zafar_train, y_zafar_train, x_control_train = ut.conversion(X[train_index], y[train_index],dict(temp_x_control_train), 1)

                    x_zafar_test, y_zafar_test, x_control_test = ut.conversion(X[test_index], y[test_index],dict(temp_x_control_test), 1)

                    threads.append(Process(target=train_zafar, args=(x_zafar_train, y_zafar_train, x_control_train,
                                                                     x_zafar_test, y_zafar_test, x_control_test,
                                                                     cons_params, loss_function, EPS,
                                                                     dataset + suffixes[proc], mutex[proc],
                                                                     sensitive_attrs)))
                elif proc == 0:
                    threads.append(Process(target=train_hardt, args=(X_train, X_test, y_train, y_test, X_valid, y_valid ,sa_index,p_Group, dataset + suffixes[proc], mutex[proc])))

                # elif proc == 5:
                #     if dataset == "kdd":
                #         proc = 4
                #     threads.append(Process(target=train_pleiss, args=(X_train, X_test, y_train, y_test, X_valid, y_valid, sa_index, dataset + suffixes[proc], mutex[proc])))
                #     proc = 5

    for process in threads:
        process.start()

    for process in threads:
        process.join()

    threads = []
    # print "elapsed time for k-fold iteration = " + str(time.time() - start)
    print "elapsed time = " + str(time.time() - start)

    results = []
    for suffix in suffixes:
        infile = open(dataset + suffix, 'rb')
        temp_buffer = pickle.load(infile)
        results.append(temp_buffer.performance)
        infile.close()

    plot_my_results(results, suffixes, "Images/" + dataset, dataset)
    delete_temp_files(dataset, suffixes)


def train_pleiss(X_train, X_test, y_train, y_test, X_valid, y_valid, sa_index, dataset, mutex):
    clf = LogisticRegression().fit(X_train, y_train)

    # predictions for test set
    test_set = pd.DataFrame(columns=['label', 'group', 'prediction'])
    y_test_set_pred_probs = clf.predict_proba(X_test)[:, 1]
    temp_test_y = y_test
    temp_test_y[temp_test_y == -1] = 0
    for line in range(0, len(X_test)):
        test_set.loc[line] = [temp_test_y[line], X_test[line][sa_index], y_test_set_pred_probs[line]]

    # predictions for validation set
    valid_set = pd.DataFrame(columns=['label', 'group', 'prediction'])
    y_valid_set_pred_probs = clf.predict_proba(X_valid)[:, 1]
    temp_valid_y = y_valid
    temp_valid_y[temp_valid_y == -1] = 0
    for line in range(0, len(X_valid)):
        valid_set.loc[line] = [temp_valid_y[line], X_valid[line][sa_index], y_valid_set_pred_probs[line]]

    # initialize validation set
    group_0_val_data = valid_set[valid_set['group'] == 0]
    group_1_val_data = valid_set[valid_set['group'] == 1]
    protected_val_model = calibModel(group_0_val_data['prediction'].values, group_0_val_data['label'].values)
    non_protected_val_model = calibModel(group_1_val_data['prediction'].values, group_1_val_data['label'].values)

    # tune algorithm
    _, _, mix_rates = calibModel.calib_eq_odds(protected_val_model, non_protected_val_model, 1, 1)

    # initialize test set
    protected_test_data = test_set[test_set['group'] == 0]
    non_protected_test_data = test_set[test_set['group'] == 1]
    protected_test_model = calibModel(protected_test_data['prediction'].values, protected_test_data['label'].values)
    non_protected_test_model = calibModel(non_protected_test_data['prediction'].values,non_protected_test_data['label'].values)

    # apply model
    eq_odds_protected_test_model, eq_odds_non_protected_test_model = calibModel.calib_eq_odds(protected_test_model,non_protected_test_model,1, 1,mix_rates)

    # obtain results
    results = calibModel.results(eq_odds_protected_test_model, eq_odds_non_protected_test_model)

    mutex.acquire()
    infile = open(dataset, 'rb')
    dict_to_ram = pickle.load(infile)
    infile.close()
    dict_to_ram.performance.append(results)
    outfile = open(dataset, 'wb')
    pickle.dump(dict_to_ram, outfile)
    outfile.close()
    mutex.release()

def train_hardt(X_train, X_test, y_train, y_test, X_valid, y_valid, sa_index, p_Group, dataset, mutex):
    clf = LogisticRegression().fit(X_train, y_train)

    # predictions for test set
    test_set = pd.DataFrame(columns=['label', 'group', 'prediction'])
    y_test_set_pred_probs = clf.predict_proba(X_test)[:, 1]
    temp_y = y_test
    temp_y[temp_y == -1] = 0

    for line in range(0, len(X_test)):
        test_set.loc[line] = [temp_y[line], X_test[line][sa_index], y_test_set_pred_probs[line]]

    # predictions for validation set
    valid_set = pd.DataFrame(columns=['label', 'group', 'prediction'])
    y_valid_set_pred_probs = clf.predict_proba(X_valid)[:, 1]
    temp_y = y_valid
    temp_y[temp_y == -1] = 0
    for line in range(0, len(X_valid)):
        valid_set.loc[line] = [temp_y[line], X_valid[line][sa_index], y_valid_set_pred_probs[line]]

    # initialize validation set
    group_0_val_data = valid_set[valid_set['group'] == p_Group]
    group_1_val_data = valid_set[valid_set['group'] == abs(1 - p_Group)]
    protected_val_model = Model(group_0_val_data['prediction'].values, group_0_val_data['label'].values)
    non_protected_val_model = Model(group_1_val_data['prediction'].values, group_1_val_data['label'].values)

    # tune algorithm
    _, _, mix_rates = Model.eq_odds(protected_val_model, non_protected_val_model)

    # initialize test set
    protected_test_data = test_set[test_set['group'] == p_Group]
    non_protected_test_data = test_set[test_set['group'] == abs(1- p_Group)]
    protected_test_model = Model(protected_test_data['prediction'].values, protected_test_data['label'].values)
    non_protected_test_model = Model(non_protected_test_data['prediction'].values, non_protected_test_data['label'].values)

    # apply model
    # eq_odds_protected_test_model, eq_odds_non_protected_test_model = Model.before_insertion_check_values(protected_test_model, non_protected_test_model, mix_rates)
    eq_odds_protected_test_model, eq_odds_non_protected_test_model = Model.eq_odds(protected_test_model, non_protected_test_model, mix_rates)

    # obtain results
    results = Model.results(eq_odds_protected_test_model, eq_odds_non_protected_test_model)
    mutex.acquire()
    infile = open(dataset, 'rb')
    dict_to_ram = pickle.load(infile)
    infile.close()
    dict_to_ram.performance.append(results)
    outfile = open(dataset, 'wb')
    pickle.dump(dict_to_ram, outfile)
    outfile.close()
    mutex.release()


def train_zafar(x_train, y_train, x_control_train, x_test, y_test, x_control_test, cons_params, loss_function, EPS, dataset, mutex, sensitive_attrs):

    cnt = 1
    while True:
        if cnt > 41:
            return
        try:
            w = fdm.train_model_disp_mist(x_train, y_train, x_control_train, loss_function, EPS, cons_params)
            rates, acc, balanced_acc = fdm.get_clf_stats(w, x_train, y_train, x_control_train, x_test, y_test, x_control_test, sensitive_attrs)
            print "Solved !!!"
            break
        except Exception, e:
            if cnt % 4 == 0:
                cons_params['tau'] *= 1.10
            print str(e) + ", tau = " + str(cons_params['tau'])
            cnt += 1
            pass

    results = dict()

    results["balanced_accuracy"] = balanced_acc
    results["accuracy"] = acc
    results["TPR_protected"] = rates["TPR_Protected"]
    results["TPR_non_protected"] = rates["TPR_Non_Protected"]
    results["TNR_protected"] = rates["TNR_Protected"]
    results["TNR_non_protected"] = rates["TNR_Non_Protected"]
    results["fairness"] = abs(rates["TPR_Protected"] - rates["TPR_Non_Protected"]) + abs(
        rates["TNR_Protected"] - rates["TNR_Non_Protected"])

    mutex.acquire()
    infile = open(dataset, 'rb')
    dict_to_ram = pickle.load(infile)
    infile.close()
    dict_to_ram.performance.append(results)
    outfile = open(dataset, 'wb')
    pickle.dump(dict_to_ram, outfile)
    outfile.close()
    mutex.release()


def train_classifier(X_train, X_test, y_train, y_test, sa_index, p_Group, dataset, mutex, mode, base_learners, c):
    if mode == 2:
        classifier = AdaCostClassifier(saIndex=sa_index, saValue=p_Group, n_estimators=base_learners, CSB="CSB2")
    # elif mode == 1:
    #     classifier = FairAdaCost(saIndex=sa_index, saValue=p_Group, n_estimators=base_learners, CSB="CSB1")
    # elif mode == 2:
    #     classifier = FairAdaCost(saIndex=sa_index, saValue=p_Group, n_estimators=base_learners, CSB="CSB2")
    # elif mode == 1:
    #     classifier = AccumFairAdaCost(n_estimators=base_learners, saIndex=sa_index, saValue=p_Group, CSB="CSB1", c=c)
    elif mode == 3:
        classifier = AccumFairAdaCost( n_estimators=base_learners, saIndex=sa_index, saValue=p_Group,  CSB="CSB2", c=c)

    classifier.fit(X_train, y_train)

    y_pred_probs = classifier.predict_proba(X_test)[:, 1]
    y_pred_labels = classifier.predict(X_test)

    mutex.acquire()
    infile = open(dataset, 'rb')
    dict_to_ram = pickle.load(infile)
    infile.close()
    dict_to_ram.performance.append(
        calculate_performance(X_test, y_test, y_pred_labels, y_pred_probs, sa_index, p_Group))
    outfile = open(dataset, 'wb')
    pickle.dump(dict_to_ram, outfile)
    outfile.close()
    mutex.release()


def main(dataset, iterations=5):
    run_eval(dataset,iterations)


if __name__ == '__main__':
    # main(sys.argv[1], int(sys.argv[2]))
    main("compass-gender",5)
