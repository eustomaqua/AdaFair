from multiprocessing import Process, Lock
import pickle
import os

import sys

from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split

sys.path.insert(0, 'DataPreprocessing')

import time
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from AdaCost import AdaCostClassifier
from FairAdaCost import FairAdaCost
from load_kdd import load_kdd
from load_dutch_data import load_dutch_data
from load_compas_data import load_compas_data
from load_adult_gender import load_adult_gender
from load_adult_race import load_adult_race
from load_bank import load_bank
from my_useful_functions import calculate_fairness, plot_results

class my_dict(object):
    def __init__(self, increase_cost, max_cost, step):
        self.performance = dict()
        self.weights = dict()
        self.init_arrays(increase_cost, max_cost, step)

    def init_arrays(self, increase_cost, max_cost, step):
        for i in range (increase_cost, max_cost+step, step):
            self.performance[i] = []
            self.weights[i] = []



def run_eval(dataset=None):


    if dataset == "compass":
        X, y, sa_index, p_Group  = load_compas_data()
    elif dataset == "adult-gender":
        X, y, sa_index, p_Group = load_adult_gender()
    elif dataset == "adult-race":
        X, y, sa_index, p_Group = load_adult_race()
    elif dataset == "dutch":
        X, y, sa_index, p_Group = load_dutch_data()
    elif dataset == "kdd":
        X, y, sa_index, p_Group = load_kdd()
    elif dataset == "bank":
        X, y, sa_index, p_Group = load_bank()

    print pd.Series(X[:, sa_index]).value_counts()

    iterations = 10
    increase_cost = 0
    max_cost = 30
    step = 1
    num_base_learners = 25


    original = my_dict(increase_cost, max_cost, step)
    only_costs = my_dict(increase_cost, max_cost, step)
    costs_and_votes = my_dict(increase_cost, max_cost, step)

    original_calibrated = my_dict(increase_cost, max_cost, step)
    only_costs_calibrated = my_dict(increase_cost, max_cost, step)
    costs_and_votes_calibrated = my_dict(increase_cost, max_cost, step)

    outfile1 = open( dataset+ "_original", 'wb')
    outfile2 = open( dataset+ "_only_costs", 'wb')
    outfile3 = open( dataset+ "_costs_and_votes", 'wb')

    outfile4 = open( dataset+ "_only_costs_calibrated", 'wb')
    outfile5 = open( dataset+ "_costs_and_votes_calibrated", 'wb')
    outfile6 = open( dataset+ "_original_calibrated", 'wb')

    pickle.dump(original, outfile1)
    pickle.dump(only_costs, outfile2)
    pickle.dump(costs_and_votes, outfile3)
    pickle.dump(only_costs_calibrated, outfile4)
    pickle.dump(costs_and_votes_calibrated, outfile5)
    pickle.dump(original_calibrated, outfile6)

    outfile1.close()
    outfile2.close()
    outfile3.close()
    outfile4.close()
    outfile5.close()
    outfile6.close()

    mutex1 = Lock()
    mutex2 = Lock()
    mutex3 = Lock()
    mutex4 = Lock()
    mutex5 = Lock()
    mutex6 = Lock()

    threads = []

    while increase_cost <= max_cost :
        costs = [1 + increase_cost/100., 1] # [pos , neg]
        print "cost = " + str(increase_cost) + " out of " + str(max_cost)
        for iter in range(0,iterations):
            start = time.time()
            kf = StratifiedKFold(n_splits=3, random_state=int(time.time()), shuffle=True)
            for train_index, test_index in kf.split(X,y):

                X_train, X_test = X[train_index], X[test_index]
                y_train, y_test = y[train_index], y[test_index]

                process1 = Process(target=train_original_classifier, args=(X_train, X_test, y_train, y_test, sa_index,p_Group, costs, increase_cost, dataset, mutex1,num_base_learners))
                threads.append(process1)
                #
                process2 = Process(target=train_cost_only_classifier, args=(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset, mutex2,num_base_learners))
                threads.append(process2)

                # #
                process3 = Process(target=train_cost_and_vote_classifier, args=(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset, mutex3,num_base_learners))
                threads.append(process3)



                # calibrated classifiers
                process4 = Process(target=train_cost_only_classifier_calibrated, args=(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset, mutex4,num_base_learners))
                threads.append(process4)

                process5 = Process(target=train_cost_and_vote_classifier_calibrated, args=(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset, mutex5, num_base_learners))
                threads.append(process5)

                process6 = Process(target=train_original_classifier_calibrated, args=(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset, mutex6,num_base_learners))
                threads.append(process6)

                process1.start()
                process2.start()
                process3.start()
                process4.start()
                process5.start()
                process6.start()

        for process in threads:
            process.join()
        threads = []
        print "elapsed time for k-fold iteration = " + str(time.time() - start)

        increase_cost += step

    infile = open(dataset + "_original", 'rb')
    original = pickle.load(infile)
    infile.close()

    infile = open(dataset + "_only_costs", 'rb')
    only_costs = pickle.load(infile)
    infile.close()

    infile = open(dataset + "_costs_and_votes", 'rb')
    costs_and_votes = pickle.load(infile)
    infile.close()


    # calibrated classifiers
    infile = open(dataset + "_only_costs_calibrated", 'rb')
    only_costs_calibrated = pickle.load(infile)
    infile.close()

    infile = open(dataset + "_costs_and_votes_calibrated", 'rb')
    costs_and_votes_calibrated = pickle.load(infile)
    infile.close()

    infile = open(dataset + "_original_calibrated", 'rb')
    original_calibrated = pickle.load(infile)
    infile.close()

    if not os.path.exists("Images/"+dataset):
        os.makedirs("Images/"+dataset)

    plot_results(0, max_cost, step, original.performance, original.weights, "Images/"+dataset + "/original", "Original AdaCost")
    plot_results(0, max_cost, step, only_costs.performance, only_costs.weights, "Images/"+dataset + "/only_costs", "AdaCost with dynamic costs")
    plot_results(0, max_cost, step, costs_and_votes.performance, costs_and_votes.weights, "Images/"+dataset + "/fully_fair", "AdaCost with dynamic costs and fair votes", False)

    # calibrated
    plot_results(0, max_cost, step, only_costs_calibrated.performance, only_costs_calibrated.weights, "Images/"+dataset + "/only_costs_calibrated", "AdaCost-Calibrated with dynamic costs", False)
    plot_results(0, max_cost, step, costs_and_votes_calibrated.performance, costs_and_votes_calibrated.weights, "Images/"+dataset + "/costs_and_votes_calibrated", "AdaCost-Calibrated with dynamic costs and fair votes", False)
    plot_results(0, max_cost, step, original_calibrated.performance, original_calibrated.weights, "Images/"+dataset + "/original_calibrated", "Original AdaCost-Calibrated", False)


def train_original_classifier_calibrated(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset,mutex,num_base_learners):

    only_costs_classifier_calibrated = FairAdaCost(saIndex=sa_index, saValue=p_Group, costs=costs, n_estimators=num_base_learners, useFairVoting=True)
    only_costs_classifier_calibrated.fit(X_train, y_train)

    sigmoid = CalibratedClassifierCV(only_costs_classifier_calibrated, method='sigmoid',cv="prefit")
    sigmoid.fit(X_train,y_train)

    y_pred_probs = sigmoid.predict_proba(X_test)[:, 1]
    y_pred_labels = sigmoid.predict(X_test)

    mutex.acquire()
    infile = open(dataset + "_costs_and_votes_calibrated", 'rb')
    costs_and_votes_calibrated = pickle.load(infile)
    infile.close()
    costs_and_votes_calibrated.performance[increase_cost].append(calculate_fairness(X_test, y_test, y_pred_labels, y_pred_probs, sa_index, p_Group))
    outfile = open( dataset+ "_costs_and_votes_calibrated", 'wb')
    pickle.dump(costs_and_votes_calibrated, outfile)
    outfile.close()
    mutex.release()

def train_cost_and_vote_classifier_calibrated(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset,mutex,num_base_learners):

    original_classifier_calibrated = AdaCostClassifier(saIndex=sa_index, saValue=p_Group, costs=costs, n_estimators=num_base_learners )
    original_classifier_calibrated.fit(X_train, y_train)

    sigmoid = CalibratedClassifierCV(original_classifier_calibrated, method='sigmoid',cv="prefit")
    sigmoid.fit(X_train,y_train)

    y_pred_probs = sigmoid.predict_proba(X_test)[:, 1]
    y_pred_labels = sigmoid.predict(X_test)

    mutex.acquire()
    infile = open(dataset + "_original_calibrated", 'rb')
    original_calibrated = pickle.load(infile)
    infile.close()
    original_calibrated.performance[increase_cost].append(calculate_fairness(X_test, y_test, y_pred_labels, y_pred_probs, sa_index, p_Group))
    outfile = open( dataset+ "_original_calibrated", 'wb')
    pickle.dump(original_calibrated, outfile)
    outfile.close()
    mutex.release()


def train_cost_only_classifier_calibrated(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset,mutex,num_base_learners):

    only_costs_classifier_calibrated = FairAdaCost(saIndex=sa_index, saValue=p_Group, costs=costs, n_estimators=num_base_learners)
    only_costs_classifier_calibrated.fit(X_train, y_train)

    sigmoid = CalibratedClassifierCV(only_costs_classifier_calibrated, method='sigmoid',cv="prefit")
    sigmoid.fit(X_train,y_train)

    y_pred_probs = sigmoid.predict_proba(X_test)[:, 1]
    y_pred_labels = sigmoid.predict(X_test)

    mutex.acquire()
    infile = open(dataset + "_only_costs_calibrated", 'rb')
    only_costs_calibrated = pickle.load(infile)
    infile.close()
    only_costs_calibrated.performance[increase_cost].append(calculate_fairness(X_test, y_test, y_pred_labels, y_pred_probs, sa_index, p_Group))
    outfile = open( dataset+ "_only_costs_calibrated", 'wb')
    pickle.dump(only_costs_calibrated, outfile)
    outfile.close()
    mutex.release()


def train_original_classifier(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset, mutex, num_base_learners):
    original_classifier = AdaCostClassifier(saIndex=sa_index, saValue=p_Group, costs=costs, n_estimators=num_base_learners )
    original_classifier.fit(X_train, y_train)
    y_pred_probs = original_classifier.decision_function(X_test)
    y_pred_labels = original_classifier.predict(X_test)

    mutex.acquire()

    infile = open(dataset + "_original", 'rb')
    original = pickle.load(infile)
    infile.close()
    original.performance[increase_cost].append(calculate_fairness(X_test, y_test, y_pred_labels, y_pred_probs, sa_index, p_Group))
    original.weights[increase_cost].append(original_classifier.get_weights())
    outfile = open( dataset+ "_original", 'wb')
    pickle.dump(original, outfile)
    outfile.close()
    mutex.release()

def train_cost_only_classifier(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset,mutex,num_base_learners):
    only_costs_classifier = FairAdaCost(saIndex=sa_index, saValue=p_Group, costs=costs, n_estimators=num_base_learners)
    only_costs_classifier.fit(X_train, y_train)
    y_pred_probs = only_costs_classifier.decision_function(X_test)
    y_pred_labels = only_costs_classifier.predict(X_test)

    mutex.acquire()

    infile = open(dataset + "_only_costs", 'rb')
    only_costs = pickle.load(infile)
    infile.close()
    only_costs.performance[increase_cost].append(calculate_fairness(X_test, y_test, y_pred_labels, y_pred_probs, sa_index, p_Group))
    only_costs.weights[increase_cost].append(only_costs_classifier.get_weights())
    outfile = open( dataset+ "_only_costs", 'wb')
    pickle.dump(only_costs, outfile)
    outfile.close()
    mutex.release()



def train_cost_and_vote_classifier(X_train, X_test, y_train, y_test, sa_index,p_Group, costs,  increase_cost, dataset, mutex,num_base_learners):
    full_classifier = FairAdaCost(saIndex=sa_index, saValue=p_Group, costs=costs, n_estimators=num_base_learners, useFairVoting=True)
    full_classifier.fit(X_train, y_train)
    y_pred_probs = full_classifier.decision_function(X_test)
    y_pred_labels = full_classifier.predict(X_test)
    mutex.acquire()

    infile = open(dataset + "_costs_and_votes", 'rb')
    costs_and_votes = pickle.load(infile)
    infile.close()

    costs_and_votes.performance[increase_cost].append(calculate_fairness(X_test, y_test, y_pred_labels, y_pred_probs, sa_index, p_Group))
    costs_and_votes.weights[increase_cost].append(full_classifier.get_weights())

    outfile = open( dataset+ "_costs_and_votes", 'wb')

    pickle.dump(costs_and_votes, outfile)
    outfile.close()
    mutex.release()


def main(dataset):
    starting= time.time()
    run_eval(dataset)

    print time.time() - starting

if __name__ == '__main__':
    main(sys.argv[1])
    # main("compass")