#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar  3 17:27:19 2020

@author: fred
Miscellaneous utilities (may be split at some point):
    ++ Management of backends (custom for various users)
    ++ GPyOpt related functions
    ++ Manages saving optimizer results
    ++ Results class added (not backwards compatible before 07/04/2020)
    
TODO: (FRED) Happy to deprecate add_path_GPyOpt/get_path_GPyOpt
    
"""
# list of * contents
__all__ = [
    # Backend utilities
    'BackendManager',
    'Batch',
    'SafeString',
    # safe string instance
    'safe_string',
    # BO related utilities
    'add_path_GPyOpt',
    'get_path_GPyOpt',
    'get_best_from_bo',
    'gen_res',
    'gen_default_argsbo',
    'gen_random_str',
    'gen_ro_noisemodel',
    'gen_pkl_file',
    'gate_maps',
    'Results',
    # Qiskit WPO utilities
    'get_H2_data',
    'get_H2_qubit_op',
    'get_H2_shift',
    'get_LiH_data',
    'get_LiH_qubit_op',
    'get_LiH_shift',
    'get_TFIM_qubit_op',
    'get_KH1_qubit_op',
    'get_KH2_qubit_op',
    'enforce_qubit_op_consistency'
]
import pdb
import dill
import string
import random
import copy
import os, socket, sys

import numpy as np
import qiskit as qk
import matplotlib.pyplot as plt

from qiskit.quantum_info import Pauli
# qiskit noise modules
from qiskit.providers.aer.noise import NoiseModel
from qiskit.providers.aer import noise
from qiskit.providers.aer.noise.errors import ReadoutError
# qiskit chemistry objects
from qiskit.chemistry import FermionicOperator
from qiskit.chemistry.drivers import PySCFDriver, UnitsType
from qiskit.aqua.operators import Z2Symmetries, WeightedPauliOperator

NoneType = type(None)
pi = np.pi

NB_SHOTS_DEFAULT = 256
OPTIMIZATION_LEVEL_DEFAULT = 1
FULL_LIST_DEVICES = ['ibmq_rochester', 'ibmq_paris', 'ibmq_singapore', 
            'ibmq_qasm_simulator'] # '', ibmq_poughkeepsie
# There may be more free devices
FREE_LIST_DEVICES = ['ibmq_16_melbourne', 
                     'ibmq_vigo', 
                     'ibmq_armonk',
                     'ibmq_essex',
                     'ibmq_burlington',
                     'ibmq_london',
                     'ibmq_rome',
                     'qasm_simulator']

# ------------------------------------------------------
# Back end management related utilities
# ------------------------------------------------------
class BackendManager():
    """ Custom backend manager to deal with different users
    self.LIST_DEVICES : list of devices accessible to the user
    self.simulator: 'qasm_simulator' backend
    self.current_backend: 'current' backend by default the simulator but which 
        can be set updated by using get_backend method with inplace=True
    
    """
    def __init__(self):
        provider_free = qk.IBMQ.load_account()
        if 'kkhosla' in os.getcwd() or 'kiran' in os.getcwd():
            self.LIST_OF_DEVICES = FULL_LIST_DEVICES
            provider_imperial = qk.IBMQ.get_provider(hub='ibmq', group='samsung', project='imperial')
            self.provider_list = {'free':provider_free, 'imperial':provider_imperial}
        else:
            self.LIST_OF_DEVICES = FREE_LIST_DEVICES
            self.provider_list = {'free':provider_free}
        self.simulator = qk.Aer.get_backend('qasm_simulator')
        self.current_backend = self.simulator
       

    # backend related utilities
    def print_backends(self):
        """List all providers by deafult or print your current provider"""
        #provider_list = {'Imperial':provider_free, 'Free':provider_imperial}
        for pro_k, pro_v in self.provider_list.items():
            print(pro_k)
            print('\n'.join(str(pro_v.backends()).split('IBMQBackend')))
            print('\n') 
        try:
            print('current backend:')
            print(self.current_backend.status())
        except:
            pass

    # backend related utilities
    def get_backend(self, name, inplace=False):
        """ Gets back end preferencing the IMPERIAL provider
        Can pass in a named string or number corresponding to get_current_status output
        Comment: The name may be confusing as a method with the same name exists in qiskit
        """
        # check if simulator is chose
        if name == len(self.LIST_OF_DEVICES) or name == 'qasm_simulator':
            temp = self.simulator
        else: # otherwise look for number/name
            if type(name) == int: name = self.LIST_OF_DEVICES[name-1]
            try: #  tries imperial first
                temp = self.provider_list['imperial'].get_backend(name)
            except:
                temp = self.provider_list['free'].get_backend(name)
                
        # if inplace update the current backend
        if inplace:
            self.current_backend = temp
        return temp

    def get_current_status(self):
        """ Prints the status of each backend """
        for ct, device in enumerate(self.LIST_OF_DEVICES): # for each device
            ba = self.get_backend(device)
            print(ct+1, ':   ', ba.status()) # print status

    def gen_instance_from_current(self, nb_shots = NB_SHOTS_DEFAULT, 
                     optim_lvl = OPTIMIZATION_LEVEL_DEFAULT,
                     noise_model = None, 
                     initial_layout=None,
                     seed_transpiler=None,
                     measurement_error_mitigation_cls=None):
        """ Generate an instance from the current backend
        Not sure this is needed here: 
            + maybe building an instance should be decided in the main_script
            + maybe it should be done in the cost function
            + maybe there is no need for an instance and everything can be 
              dealt with transpile, compile
            
            ++ I've given the option to just spesify the gate order as intiial layout here
                however this depends on NB_qubits, so it more natural in the cost function
                but it has to be spesified for the instance here??? Don't know the best
                way forward. 
        """
        if type(initial_layout) == list:
            nb_qubits = len(initial_layout)
            logical_qubits = qk.QuantumRegister(nb_qubits, 'logicals')  
            initial_layout = {logical_qubits[ii]:initial_layout[ii] for ii in range(nb_qubits)}
        instance = qk.aqua.QuantumInstance(self.current_backend, shots=nb_shots,
                            optimization_level=optim_lvl, noise_model= noise_model,
                            initial_layout=initial_layout,
                            seed_transpiler=seed_transpiler,
                            measurement_error_mitigation_cls=measurement_error_mitigation_cls)
        print('Generated a new quantum instance')
        return instance

    def gen_noise_model_from_backend(self, name_backend='ibmq_essex', 
                                     readout_error=True, gate_error=True):
        """ Given a backend name (or int) return the noise model associated"""
        backend = self.get_backend(name_backend)
        properties = backend.properties()
        noise_model = noise.device.basic_device_noise_model(properties, 
                            readout_error=readout_error, gate_error=gate_error)
        return noise_model
    
      



class Batch():
    """ New class that batches circuits together for a single execute.
        MERGE: assumes optim class has .prefix (can be hashed random string)
        + Init with instatnce where all circits will be run on 
        + Use submit, to build up list of meas circs,
        + Use execute to send all the jobs to the imbq device
        + Use result to recall the results relevant to different experiments in the batch"""
    def __init__(self, instance = None):
        """
        Parameters
        ----------
        instance: a qiskit quantum instance used to to submit the jobs"""
        self.circ_list = []
        self._last_circ_list = None
        self._last_results_obj = None
        if instance == None:
            backend = qk.providers.aer.QasmSimulator()
            self.instance = qk.aqua.QuantumInstance(backend, shots=256)
        else:
            self.instance = instance
        self._known_optims = []
    
    def submit(self, obj_in, name = None):
        """ Adds new circuits requested by the optimizer to the list of circs
            to execute. 
            + Can submit optim ParallelOptimiser object directly, OR \n
            + Can submit list of circuits and a tage (used to request the results)
            
            Parameters:
            -----------
            obj_in: An instance of Parallel runner (or subclass), OR a list of circuits to run. 
            If list of circuits is submited a name must also be provided
            
            name: Input string to identify this list of circuits and return the right reduced object. 
            name is provided by the ParallelRunner object if none is provided"""
        if hasattr(obj_in, '__iter__'):
            assert name != None, " If input is a list of circuits, please provide a name"
            obj_in = list(obj_in)
            circ_list = copy.deepcopy(obj_in)
        else:  # assume input was object
            name = obj_in.prefix
            circ_list = copy.deepcopy(obj_in.circs_to_exec)
        if name in self._known_optims:
            raise AttributeError("Currently has submitted circuits of same name - please rename")
        for circ in circ_list:
            circ.name = name + circ.name
        self.circ_list += circ_list
        self._known_optims += [name]
    
    def execute(self):
        """
        Use the instance provided to submit a single job list to"""
        results = self.instance.execute(self.circ_list, had_transpiled=True)
        self._last_results_obj = results
        self._last_circ_list = self.circ_list
        self.circ_list = []
        self._known_optims = []
    
    def result(self, obj_in):
        """
        Returns a results object as though it was generated by executing the list of circuits. 
        
        Parameters: 
        ---------
        obj_in: Either a ParallelRunner instance, or string that was used to lable during Batch.submit()
        """
        if type(obj_in) == str:
            name = obj_in
        else:
            name = obj_in.prefix
        results_di = self._last_results_obj.to_dict()
        relevant_results = []
        for experiment in results_di['results']:
            if name in experiment['header']['name']:
                experiment['header']['name'] = experiment['header']['name'].split(name)[1]
                # _round_res_dict(experiment['data']['counts'])
                relevant_results.append(experiment)
        results_di['results'] = relevant_results
        results_obj = qk.result.result.Result.from_dict(results_di)
        if type(obj_in) != str:
            obj_in._last_results_obj = results_obj
        return results_obj
    
    def submit_exec_res(self, obj_in, name = None):
        """
        Submits, executs and returns the results object in one go
        
        Parameters:
        -------------
        obj_in:
            Runner instance or list of circuits to execute
        
        name:
            String to identify cricuits (must be spesified if obj_in is a list of circs)
        """
        self.submit(obj_in, name)
        self.execute()
        if type(obj_in) == list:
            return self.result(name)
        else:
            return self.result(obj_in)
    
    def flush(self):
        """
        Flushes everything, effectively a hard reset
        """
        self.circ_list = []
        self._last_circ_list = None
        self._last_results_obj = None    
        self._known_optims = []


class SafeString():
    """ This class keeps track of previous random strings and guarantees that
        the next random string has not been used before since the object was 
        constructed\n
        avoid_on_init: (default: None) a string, or list of strings that you want SafeString to avoud
        ----
        TODO: allow to decide, lower, upper, etc...
        TODO: allow ability to seed sequence"""
    def __init__(self, avoid_on_init = None):

        if type(avoid_on_init) == NoneType:
            self._previous_random_objects = []
        elif type(avoid_on_init) == str:
            self._previous_random_objects = [avoid_on_init]
        elif type(avoid_on_init) == list:
            self._previous_random_objects = avoid_on_init
    def gen(self, nb_chars = 3):
        """ Generate a guaranteed new random string for given length \n
            nb_chars: (default: 3) length of string you want to gen"""
        new_string = gen_random_str(nb_chars = nb_chars)
        ct = 0
        while new_string in self._previous_random_objects:
            new_string = gen_random_str(nb_chars = nb_chars)
            ct+=1
        if ct>50:
            print("Warning in SafeString: consider increasing length of requested string")
        self._previous_random_objects.append(new_string)
        return new_string

# module level instance
safe_string = SafeString()

def quick_instance():
    simulator = qk.Aer.get_backend('qasm_simulator')
    inst = qk.aqua.QuantumInstance(simulator, shots=512, optimization_level=1)
    return inst


def append_measurements(circuit, measurements, logical_qubits=None):
    """ Append measurements to one circuit:
        TODO: Replace with Weighted pauli ops?"""
    circ = copy.deepcopy(circuit)
    num_creg = len(measurements.replace('1',''))
    if num_creg > 0:
        cr = qk.ClassicalRegister(num_creg, 'classical')
        circ.add_register(cr)
    if logical_qubits is None: 
        logical_qubits = np.arange(circ.num_qubits)
    creg_idx = 0
    for qb_idx, basis in enumerate(measurements):
        qubit_number = logical_qubits[qb_idx]
        if basis == 'z':
            circ.measure(qubit_number, creg_idx)
            creg_idx += 1
        elif basis == 'x':
            circ.u2(0.0, pi, qubit_number)  # h
            circ.measure(qubit_number, creg_idx)
            creg_idx += 1
        elif basis == 'y':
            circ.u1(-np.pi / 2, qubit_number)  # sdg
            circ.u2(0.0, pi, qubit_number)  # h
            circ.measure(qubit_number, creg_idx)
            creg_idx += 1
        elif basis != '1':
            raise NotImplementedError('measurement basis {} not understood').format(basis)
    return circ


def gen_meas_circuits(main_circuit, meas_settings, logical_qubits=None):
    """ MOVE FROM COST  Return a list of measurable circuit based on a main circuit and
    different settings"""
    c_list = [append_measurements(main_circuit.copy(), m, logical_qubits) 
                  for m in meas_settings] 
    return c_list
# ------------------------------------------------------
# BO related utilities
# ------------------------------------------------------
def add_path_GPyOpt():
    sys.path.insert(0, get_path_GPyOpt())
            
def get_path_GPyOpt():
    """ Generate the path where the package GPyOpt should be found, 
    this is custom to the user/machine
    GPyOpt version is from the  fork https://github.com/FredericSauv/GPyOpt
    """
    if 'fred' in os.getcwd(): 
        if 'GIT' in os.getcwd():
            path = '/home/fred/Desktop/WORK/GIT/GPyOpt'
        else:
            path = '/home/fred/Desktop/GPyOpt/'
    elif 'level12' in socket.gethostname():
        path = '/home/kiran/QuantumOptimization/GPyOpt/'
    elif 'Lambda' in socket.gethostname():
        path = '/home/kiran/Documents/onedrive/Active_Research/QuantumSimulation/GPyOpt'
    else:
        path = ''
    return path

def get_best_from_bo(bo):
    """ Extract from a BO object the best set of parameters and fom
    based on from observed data and model"""
    x_obs = bo.X[np.argmin(bo.Y),:] #bo.x_opt
    y_obs = np.min(bo.Y) #bo.fx_opt 
    pred = bo.model.predict(bo.X, with_noise=False)[0]
    x_pred = bo.X[np.argmin(pred)]
    y_pred = np.min(pred)
    return (x_obs, y_obs), (x_pred, y_pred)

def gen_res(bo):
    """ Generate a dictionary from a BO object to be stored"""
    (x_obs, y_obs), (x_pred, y_pred) = get_best_from_bo(bo)
    res = {'x_obs':x_obs, 
           'x_pred':x_pred, 
           'y_obs':y_obs, 
           'y_pred':y_pred,
           'X':bo.X, 
           'Y':bo.Y, 
           'gp_params':bo.model.model.param_array,
           'gp_params_names':bo.model.model.parameter_names()}
    return res

def gen_default_argsbo(f, domain, nb_init, eval_init=False):
    """ maybe unnecessary"""
    default_args = {
           'model_update_interval':1, 
           'hp_update_interval':5, 
           'acquisition_type':'LCB', 
           'acquisition_weight':5, 
           'acquisition_weight_lindec':True, 
           'optim_num_anchor':5, 
           'optimize_restarts':1, 
           'optim_num_samples':10000, 
           'ARD':False}
    
    domain_bo = [{'name': str(i), 'type': 'continuous', 'domain': d} 
                 for i, d in enumerate(domain)]
    # Generate random x uniformly (could implement other randomness) if not provided
    if eval_init:
        x_init = np.transpose([np.random.uniform(*d, size = nb_init) for d in domain])
        y_init = f(x_init)
        numdata_init=None
    else:
        y_init = None
        x_init = None
        numdata_init = nb_init
        
    default_args.update({'f':f, 'domain':domain_bo, 'X':x_init, 'Y':y_init,
                         'initial_design_numdata': numdata_init})

    return default_args

def gen_random_str(nb_chars = 5):
    """ Returns random string of arb length: inc lower, UPPER and digits"""
    choose_from = string.ascii_letters + string.digits
    rnd = ''.join([random.choice(choose_from) for ii in range(nb_chars)])
    return rnd

def prefix_to_names(circ_list, st_to_prefix):
    """ Returns a NEW list of circs with new names appended"""
    circ_list = copy.deepcopy(circ_list)
    for ii in range(len(circ_list)):
        circ_list[ii].name = st_to_prefix + circ_list[ii].name 
    return circ_list


# Generate noise models
def gen_ro_noisemodel(err_proba = [[0.1, 0.1],[0.1,0.1]], qubits=[0,1]): 
    noise_model = NoiseModel()
    for ro, q in zip(err_proba, qubits):
        err = [[1 - ro[0], ro[0]], [ro[1], 1 - ro[1]]]
        noise.add_readout_error(ReadoutError(err), [q])
    return noise_model

# Save data from the cost fucntion and opt
def gen_pkl_file(
    cost,
    Bopt,
    baseline_values = None, 
    bopt_values = None,
    info = '',
    path = '',
    file_name = None,
    dict_in = None,
    ):
    """ Streamlines save"""
    
    if file_name is None:
        file_name = path + '_res_' + cost.instance.backend.name() 
        file_name += '_' + str(cost.__class__).split('.')[1].split("'")[0] + '_'
        file_name += info
        file_name += gen_random_str(3)
        file_name += '.pkl'

    
    res_to_dill = gen_res(Bopt)
    dict_to_dill = {'bopt_results':res_to_dill, 
                    'cost_baseline':baseline_values, 
                    'cost_bopt':bopt_values,
                    'depth':cost.get_depth(-1),
                    'ansatz':cost.main_circuit,
                    'meta':cost._res,
                    'other':dict_in}

    with open(file_name, 'wb') as f:                                                                                                                                                                                                          
        dill.dump(dict_to_dill, f)                                                                                                                                                                                                            

def gate_maps(arg):
    """ Stores usefull layouts for different devices"""
    gate_maps_di = {'SINGAPORE_GATE_MAP_CYC_6': [1,2,3,8,7,6], # Maybe put this in bem
                    'SINGAPORE_GATE_MAP_CYC_6_EXTENDED':[2, 6, 10, 12, 14, 8], # Maybe put this in bem
                    'ROCHESTER_GATE_MAP_GHZ_3_SWAPSx0':[1,3,2],
                    'ROCHESTER_GATE_MAP_GHZ_3_SWAPSx1':[0,3,2],
                    'ROCHESTER_GATE_MAP_GHZ_3_SWAPSx2':[0,4,2],
                    'ROCHESTER_GATE_MAP_GHZ_3_SWAPSx3':[0,6,2],    
                    'ROCHESTER_GATE_MAP_GHZ_3_SWAPSx4':[5,6,2], # might actually be 5 dheck/rerun
                    'ROCHESTER_GATE_MAP_GHZ_3_SWAPSx5':[5,13,2], # might actually be 6 dheck/rerun
                    'ROCHESTER_GATE_MAP_GHZ_3_SWAPSx6':[9,13,2]} # might actually be 7 dheck/rerun
    if arg == 'keys':
        return gate_maps_di.keys()
    else:
        return gate_maps_di[arg]

class Results():
    import matplotlib.pyplot as plt
    """ Results class to quickly analize a pkl file
        Will be bcakward compatible with .plk from 07/04/2020"""
    def __init__(self, f_name, reduced_meta = True):
        self.name = f_name
        self.reduced_meta = reduced_meta
        self.data = self._load(f_name)

    def _load(self, f_name):
        """ Loads in a .pkl file to the object"""
        with open(f_name, 'rb') as f:
            data = dill.load(f)
        if self.reduced_meta:
            if 'meta' in data:
                data['meta'] = [data['meta'][0]]
            else:
                data['meta'] = None
        return data

    def print_all_keys(self, dict_in=None):
        """ Prints a list of keys in the loaded file - just to see whats there"""
        if dict_in == None: dict_in = self.data
        keys = dict_in.keys()
        running_tot = []
        for key in keys:
            if type(dict_in[key]) == dict:
                sub_list = self.print_all_keys(dict_in[key])
                running_tot.append(key)
                running_tot.append(sub_list)
            else:
                running_tot.append(key)
        return running_tot
    
    def plot_convergence(self):
        """ Plots the convergence of the Bopt vales (hope I've done' this right)"""
        bopt = self.data['bopt_results']
        X = bopt['X']
        Y = bopt['Y']
        plt.subplot(1, 2, 1)
        plt.plot(self._diff_between_x(X))
        plt.xlabel('itt')
        plt.ylabel('|dX_i|')
        plt.subplot(1, 2, 2)
        plt.plot(Y)
        plt.xlabel('itt')
        plt.ylabel('Y')
        plt.show()

    def plot_baselines(self,
                       same_axis=False,
                       bins=30,
                       axis=[0, 1, 0, 5]):
        """ Plots baseline histograms with mean and variance of each, comparing
            the Bopt values to the true baseilne values"""
        baseline = self.data['cost_baseline']
        baseline = np.squeeze(baseline)
        if None in baseline:
            baseline = [1]
        bopt = self.data['cost_bopt']
        bopt = np.squeeze(bopt)
        if same_axis:
            plt.hist(baseline, bins,label='base')
            plt.hist(bopt, bins,label='bopt')
            plt.xlabel('Yobs')
            plt.ylabel('count')
            plt.legend() ## add means +vars here
        else:
            plt.subplot(1, 2, 1)
            plt.hist(baseline, bins)
            mean = np.round(np.mean(baseline), 4)
            std = np.round(np.std(baseline), 4)
            plt.title('Base: mean: {} \n std: {}'.format(mean,std))
            
            plt.subplot(1, 2, 2)    
            plt.hist(bopt, bins)
            plt.xlabel('Yobs')
            plt.ylabel('count')    
            mean = np.round(np.mean(bopt), 4)
            std = np.round(np.std(bopt), 4)
            plt.title('Opt: mean: {} \n std: {}'.format(mean,std))
        plt.show()
    
    def plot_circ(self):
        """ Displays quick info about the ansatz circuit:
            TODO: Add check for transpiled ansatz circuit
                  Add log2phys mapping if avaliable"""
        circ = self.data['ansatz']
        depth = self.data['depth']
        try:
            meta = self.data['meta'][0]
        except:
            meta = {'backend_name':'device'}
        fig, ax = plt.subplots(1,1)
        circ.draw(output='mpl',ax=ax,scale=0.4, idle_wires=False)
        plt.title('Backend: {} \n Circuit depths = {} \pm {}'.format(meta['backend_name'], np.mean(depth), np.std(depth)))
        plt.show()
            
    def plot_final_params(self,
                     x_sol=None):
        """ Compares Predicted, observed and analytic (input spesified) parameter 
            solutions. """
        bopt = self.data['bopt_results']
        x_obs = bopt['x_obs']
        x_pred = bopt['x_pred']
        y_obs = np.round(bopt['y_obs'], 3)
        y_pred = np.round(bopt['y_pred'], 3)
        
        plt.plot(x_obs, 'rd', label='obs: ({})'.format(y_obs))
        plt.plot(x_pred, 'k*', label='pred: ({})'.format(y_pred))
        if type(x_sol) == NoneType:
            try:
                x_sol = self.data['other']['x_sol']
            except:
                pass
        if type(x_sol) != type(None):
            plt.plot(x_sol, 'bo', label='sol: ({})'.format(1))
            x_sol = np.array(x_sol)
        plt.legend()
        plt.xlabel('Parameter #')
        plt.ylabel('Parameter value')
        plt.title('Sol vs Seen')# (Dist = {})'.format(np.round(distance,4)))
        plt.show()
    
    def plot_param_trajectories(self):
        """ Plots the convergence of the Bopt vales (hope I've done' this right)"""
        bopt = self.data['bopt_results']
        X = bopt['X']
        nb_params = len(X[0])
        plt_x, plt_y = self._decide_plot_layout(nb_params)
        fig, ax_vec = plt.subplots(plt_x, plt_y, sharex=True, sharey=True)
        ax_vec = [ax_vec[ii][jj] for ii in range(plt_x) for jj in range(plt_y)]
        for ii in range(nb_params):
            ax_vec[ii].plot(X[:,ii])
            ax_vec[ii].set_title('param #{}'.format(str(ii)))
        fig.add_subplot(111, frameon=False) 
        plt.tick_params(labelcolor='none', top=False, bottom=False, left=False, right=False)
        plt.xlabel("itter")
        plt.ylabel("angle")
        plt.show()
    
    def bopt_summary(self):
        bopt = self.data['bopt_results']
        gp_params = bopt['gp_params']
        gp_params_names = bopt['gp_params_names']
        cost_baseline = self.data['cost_baseline']
        cost_baseline = np.squeeze(cost_baseline)
        if None in cost_baseline: cost_baseline = [1]
        cost_bopt = self.data['cost_bopt']
        cost_bopt = np.squeeze(cost_bopt)
        temp_bl = [np.mean(cost_baseline),np.std(cost_baseline)]
        temp_bo = [np.mean(cost_bopt), np.std(cost_bopt)]
        improvement = 100*(temp_bo[0] / temp_bl[0] - 1)
        CI = improvement / (100* np.sqrt(temp_bo[1] * temp_bl[1]  ))
         
        print('Bopt params')
        self._print_helper(gp_params_names, gp_params)
        print('\n')
        print('Baseline stats')
        self._print_helper(['mean', 'standard dev.'], temp_bl)
        print('Bopt stats')
        self._print_helper(['mean', 'standard dev.'], temp_bo)
        print('Net Improvement')
        self._print_helper(['% improvement', 'relative to sigma'], [improvement, CI])
    
    def quick_summary(self):
        self.bopt_summary()
        self.plot_baselines(same_axis=True)
        self.plot_convergence()
        self.plot_final_params()
        self.plot_param_trajectories()
        self.plot_circ()
 
    # These don't really need to be in the class, but thought I'd hid them here to reduce ut
    def _diff_between_x(self, X_in):
        """ Computes the euclidian distance between adjacent X values
        + Might need to vectorize this in future"""
        dX = X_in[1:] - X_in[0:-1]
        dX = [dx.dot(dx) for dx in dX]
        dX = np.sqrt(np.array(dX))
        return dX
    
    def _decide_plot_layout(self, n):
        if n < 3:
            return n, 1
        elif n == 4:
            return 2, 2
        elif n > 4 and n <= 6:
            return 2, 3
        elif n > 6 and n <= 9:
            return 3, 3
        elif n > 9 and n <= 15:
            return 3, 5
        elif n == 16:
            return 4, 4
        elif n > 16:
            x = int(np.ceil(np.sqrt(n)))
            return x, x
    
    def _print_helper(self, key, val, min_len = 25):
        for ii in range(len(key)):
            temp_v = val[ii]
            if type(temp_v) == float or type(temp_v) == int or type(temp_v) == np.float64:
                temp_v = '%s' % float('%.3g' % val[ii])
            else:
                temp_v = val[ii]
            if len(key[ii]) < min_len:
                pad_len = min_len - len(key[ii])
                pree = ' '*pad_len
                temp_k = pree + key[ii]
                
            print(temp_k + ':  ' + temp_v)

# ------------------------------------------------------
# Qiskit WPO related helper functions
# ------------------------------------------------------

def get_H2_data(dist):
    """ 
    Use the qiskit chemistry package to get the qubit Hamiltonian for LiH

    Parameters
    ----------
    dist : float
        The nuclear separations

    Returns
    -------
    qubitOp : qiskit.aqua.operators.WeightedPauliOperator
        Qiskit representation of the qubit Hamiltonian
    shift : float
        The ground state of the qubit Hamiltonian needs to be corrected by this amount of
        energy to give the real physical energy. This includes the replusive energy between
        the nuclei and the energy shift of the frozen orbitals.
    """
    # I have experienced some crashes
    from qiskit.chemistry import QiskitChemistryError
    _retries = 50
    for i in range(_retries):
        try:
            driver = PySCFDriver(atom="H .0 .0 .0; H .0 .0 " + str(dist), 
                                 unit=UnitsType.ANGSTROM, 
                                 charge=0, 
                                 spin=0, 
                                 basis='sto3g',
                                )
            molecule = driver.run()
            repulsion_energy = molecule.nuclear_repulsion_energy
            num_particles = molecule.num_alpha + molecule.num_beta
            num_spin_orbitals = molecule.num_orbitals * 2
            ferOp = FermionicOperator(h1=molecule.one_body_integrals, h2=molecule.two_body_integrals)
            qubitOp = ferOp.mapping(map_type='parity', threshold=1E-8)
            qubitOp = Z2Symmetries.two_qubit_reduction(qubitOp,num_particles)
            shift = repulsion_energy
            break
        except QiskitChemistryError:
            if i==(_retries-1):
                raise
            pass


    return qubitOp, shift

def get_H2_qubit_op(dist):
    """
    Wrapper around get_H2_data to only return the qubit operators
    """
    qubitOp, shift = get_H2_data(dist)
    return qubitOp

def get_H2_shift(dist):
    """
    Wrapper around get_H2_data to only return the energy shift
    """
    qubitOp, shift = get_H2_data(dist)
    return shift

def get_LiH_data(dist):
    """ 
    Use the qiskit chemistry package to get the qubit Hamiltonian for LiH

    Parameters
    ----------
    dist : float
        The nuclear separations

    Returns
    -------
    qubitOp : qiskit.aqua.operators.WeightedPauliOperator
        Qiskit representation of the qubit Hamiltonian
    shift : float
        The ground state of the qubit Hamiltonian needs to be corrected by this amount of
        energy to give the real physical energy. This includes the replusive energy between
        the nuclei and the energy shift of the frozen orbitals.
    """
    # I have experienced some crashes
    from qiskit.chemistry import QiskitChemistryError
    _retries = 50
    for i in range(_retries):
        try:
            driver = PySCFDriver(atom="Li .0 .0 .0; H .0 .0 " + str(dist), 
                                 unit=UnitsType.ANGSTROM, 
                                 charge=0, 
                                 spin=0, 
                                 basis='sto3g',
                                )
            molecule = driver.run()
            freeze_list = [0]
            remove_list = [-3, -2]
            repulsion_energy = molecule.nuclear_repulsion_energy
            num_particles = molecule.num_alpha + molecule.num_beta
            num_spin_orbitals = molecule.num_orbitals * 2
            remove_list = [x % molecule.num_orbitals for x in remove_list]
            freeze_list = [x % molecule.num_orbitals for x in freeze_list]
            remove_list = [x - len(freeze_list) for x in remove_list]
            remove_list += [x + molecule.num_orbitals - len(freeze_list)  for x in remove_list]
            freeze_list += [x + molecule.num_orbitals for x in freeze_list]
            ferOp = FermionicOperator(h1=molecule.one_body_integrals, h2=molecule.two_body_integrals)
            ferOp, energy_shift = ferOp.fermion_mode_freezing(freeze_list)
            num_spin_orbitals -= len(freeze_list)
            num_particles -= len(freeze_list)
            ferOp = ferOp.fermion_mode_elimination(remove_list)
            num_spin_orbitals -= len(remove_list)
            qubitOp = ferOp.mapping(map_type='parity', threshold=1E-8)
            #qubitOp = qubitOp.two_qubit_reduced_operator(num_particles)
            qubitOp = Z2Symmetries.two_qubit_reduction(qubitOp,num_particles)
            shift = repulsion_energy + energy_shift
            break
        except QiskitChemistryError:
            if i==(_retries-1):
                raise
            pass

    return qubitOp, shift

def get_LiH_qubit_op(dist):
    """
    Wrapper around get_LiH_data to only return the qubit operators
    """
    qubitOp, shift = get_LiH_data(dist)
    return qubitOp

def get_LiH_shift(dist):
    """
    Wrapper around get_LiH_data to only return the energy shift
    """
    qubitOp, shift = get_LiH_data(dist)
    return shift

def get_TFIM_qubit_op(
    N,
    B=1,
    J=1,
    pbc=False,
    resolve_degeneracy=False,
    ):
    """ 
    Construct the qubit Hamiltonian for 1d TFIM: H = \sum_{i} ( J Z_i Z_{i+1} + B X_i )

    Parameters
    ----------
    N : int
        The number of spin 1/2 particles in the chain
    B : float, default 1.
        Transverse field strength
    J : float, default 1.
        Ising interaction strength
    pbc : boolean, optional default False
        Set the boundary conditions of the 1d spin chain
    resolve_degeneracy : boolean, optional default False
        Lift the ground state degeneracy (when |B*J| < 1) with a small Z field

    Returns
    -------
    qubitOp : qiskit.aqua.operators.WeightedPauliOperator
        Qiskit representation of the qubit Hamiltonian
    """

    pauli_terms = []

    # ZZ terms
    pauli_terms += [ (-J,Pauli.from_label('I'*(i)+'ZZ'+'I'*((N-1)-(i+1)))) for i in range(N-1) ]
    # optional periodic boundary condition term
    if pbc:
        pauli_terms += [ (-J,Pauli.from_label('Z'+'I'*(N-2)+'Z')) ]
    # for B*J<1 the ground state is degenerate, can optionally lift that degeneracy with a 
    # small Z field
    if resolve_degeneracy:
        pauli_terms += [ (np.min([J,B])*1E-3,Pauli.from_label('I'*(i)+'Z'+'I'*(N-(i+1)))) for i in range(N) ]
    
    # X terms
    pauli_terms += [ (-B,Pauli.from_label('I'*(i)+'X'+'I'*(N-(i+1)))) for i in range(N) ]

    qubitOp = WeightedPauliOperator(pauli_terms)

    return qubitOp

def get_KH1_qubit_op(Jx,Jy,Jz,v=1.,Jrand=0.,seed=0):
    """ 
    Construct the qubit Hamiltonian for one loop of the Kitaev Ladder:

    0   1
    o---o
    |   |
    o-.-o
    2   3

    | : Jz
    --- : Jx
    -.- : Jy

    Parameters
    ----------
    Jx, Jy, Jz : floats
        The coupling parameters of the model (labelled above)
    v : float, optional
        Optionally multiply the 1-3 ZZ term by `v` to insert a vortex
    Jrand : float, optional
        Strength of the randomness that can be added to all Ji couplings to 
        resolve the degeneracy of the model.
    seed : int, optional
        Seed for the randomness added to the Ji couplings

    Returns
    -------
    qubitOp : qiskit.aqua.operators.WeightedPauliOperator
        Qiskit representation of the qubit Hamiltonian
    """
    from numpy.random import default_rng
    rng = default_rng(seed=seed)

    pauli_terms = []

    # ZZ terms
    pauli_terms.append((Jz+Jrand*rng.uniform(-1,+1),Pauli.from_label('ZIZI')))
    pauli_terms.append((Jz*v+Jrand*rng.uniform(-1,+1),Pauli.from_label('IZIZ')))
    # XX term
    pauli_terms.append((Jx+Jrand*rng.uniform(-1,+1),Pauli.from_label('XXII')))
    # YY term
    pauli_terms.append((Jy+Jrand*rng.uniform(-1,+1),Pauli.from_label('IIYY')))

    qubitOp = WeightedPauliOperator(pauli_terms)

    return qubitOp

def get_KH2_qubit_op(Jx,Jy,Jz,v=1.):
    """ 
    Construct the qubit Hamiltonian for two loops of the Kitaev Ladder:

    0   1   2
    o---o-.-o
    |   |   |
    o-.-o---o
    3   4   5

    | : Jz
    --- : Jx
    -.- : Jy

    Parameters
    ----------
    Jx, Jy, Jz : floats
        The coupling parameters of the model (labelled above)
    v : float, optional
        Optionally multiply the 1-4 ZZ term by `v` to insert a vortex pair

    Returns
    -------
    qubitOp : qiskit.aqua.operators.WeightedPauliOperator
        Qiskit representation of the qubit Hamiltonian
    """

    pauli_terms = []

    # ZZ terms
    pauli_terms.append((Jz,Pauli.from_label('ZIIZII')))
    pauli_terms.append((Jz*v,Pauli.from_label('IZIIZI')))
    pauli_terms.append((Jz,Pauli.from_label('IIZIIZ')))
    # XX terms
    pauli_terms.append((Jx,Pauli.from_label('XXIIII')))
    pauli_terms.append((Jx,Pauli.from_label('IIIIXX')))
    # YY terms
    pauli_terms.append((Jy,Pauli.from_label('IYYIII')))
    pauli_terms.append((Jy,Pauli.from_label('IIIYYI')))

    qubitOp = WeightedPauliOperator(pauli_terms)

    return qubitOp


def get_H_chain_data(dist_vec):
    """ 
    Use the qiskit chemistry package to get the qubit Hamiltonian for LiH

    Parameters
    ----------
    dist : float
        The nuclear separations

    Returns
    -------
    qubitOp : qiskit.aqua.operators.WeightedPauliOperator
        Qiskit representation of the qubit Hamiltonian
    shift : float
        The ground state of the qubit Hamiltonian needs to be corrected by this amount of
        energy to give the real physical energy. This includes the replusive energy between
        the nuclei and the energy shift of the frozen orbitals.
    """
    # I have experienced some crashes
    from qiskit.chemistry import QiskitChemistryError
    _retries = 50
    dist_vec = np.atleast_1d(dist_vec)
    atom = '; '.join(['H 0 0 {}'.format(dd) for dd in np.cumsum([0] + list(dist_vec))])
    for i in range(_retries):
        try:
            driver = PySCFDriver(atom=atom, 
                                 unit=UnitsType.ANGSTROM, 
                                 charge=0, 
                                 spin=(len(dist_vec)+1)%2, 
                                 basis='sto3g',
                                )
            molecule = driver.run()
            repulsion_energy = molecule.nuclear_repulsion_energy
            num_particles = molecule.num_alpha + molecule.num_beta
            num_spin_orbitals = molecule.num_orbitals * 2
            ferOp = FermionicOperator(h1=molecule.one_body_integrals, h2=molecule.two_body_integrals)
            qubitOp = ferOp.mapping(map_type='parity', threshold=1E-8)
            qubitOp = Z2Symmetries.two_qubit_reduction(qubitOp,num_particles)
            shift = repulsion_energy
            break
        except QiskitChemistryError:
            if i==(_retries-1):
                raise
            pass


    return qubitOp, shift



def enforce_qubit_op_consistency(qubit_ops):
    """
    Run the qiskit grouped basis algorithm on the set of qubit ops
    in a way that ensure the basis is common amongst all the ops.
    The makes sure that the measurement results can be shared. 

    NOTE: this is a simple approach, I tried to make this work with
    the grouping class and setting a common basis but could not get
    it to work.
    
    Parameters
    ----------
    qubit_ops : list of WeightedPauliOperator
        Operator sets to group

    Returns
    -------
    new_qubit_ops : list of WeightedPauliOperator
        Grouped operator sets with a shared common basis
    """

    for idx,qop in enumerate(qubit_ops):
        # type check
        if not type(qop) is WeightedPauliOperator:
            raise TypeError
        # ensure all ops have same number of qubits
        if idx == 0:
            num_qubits = qop.num_qubits  
        else:
            assert qop.num_qubits==num_qubits, ("Qubit operators passed"
                +" do not all have the same number of qubits.")

    # for each wpo in qubit_ops, create a dict mapping pauli->weight
    dict_qops_paulis = [ { p[1]:p[0] for p in qop.paulis } for qop in qubit_ops ]

    # go through all qubit_ops and compile set of all pauli used
    all_paulis = []
    for qop in qubit_ops:
        all_paulis += [ p[1] for p in qop.paulis if p[1] not in all_paulis ]

    # rebuild list of qubit ops with shared set of paulis and a
    # common ordering
    new_qops = []
    for qop,dqop in zip(qubit_ops,dict_qops_paulis):
        tmp_paulis = []
        for p in all_paulis:
            if p in dqop.keys():
                weight = dqop[p]
            else:
                weight = 10*qop.atol
            tmp_paulis.append((weight,p))
        new_qops.append(WeightedPauliOperator(tmp_paulis))

    return new_qops

# ------------------------------------------------------
# Hamiltonian related helper functions
# ------------------------------------------------------

def pauli_correlation(single_count_dict, ii, jj = None):
    """ 
    Returns the correlation between qubits ii and jj for the given count string
    e.g. a passing a count dict that was measuered in the Z basis computes 
    <Z_ii Z_jj> 
    
    Parameters
    ----------
    single_count_dict : dict
        The count dict of a particular measurement outcome
    ii : int
        The first qubit
    jj : int, None (default None)
        The second qubit. If None, returns expectation value of single qubit ii
    """
    corr = 0
    shots = 0
    single_qubit = jj == None
    for key in single_count_dict.keys():
        shots += single_count_dict[key]
        t1 = (int(key[ii]) - 0.5) * 2
        if single_qubit:t2 = 1
        else: t2 = (int(key[jj]) - 0.5) * 2
        corr += t1 * t2 * single_count_dict[key]
    return corr/shots


def gen_random_xy_hamiltonian(nb_spins, 
                  U = 1.0,
                  J = 1.0,
                  delta = 0.1,
                  alpha = 1.0, 
                  seed = 10):
    """
    Generates a random XY Hamiltonian. Diag elements are the field strength, 
    and off diagonal elements are the couplings rates of the XX + YY terms 
    
    H = U sigma_z + (J + delta) * (XX' + YY') / |r - r'|^alpha
    
    Parameters:
    ------
    nb_spins : int 
        nb of spins in the 1D spin chain
    U : float (default 1)
        The Z terms in H
    J : float (default 1)
        Average value of the XX+YY nearest neighbour coupling terms
    delta : float (default 0.1)
        Fluctuations in the coupling terms (also decrease with distance)
        Drawn from random uniform [0, delta] for now
    alpha : float (default 1)
        Power of the long range decay
    seed : int (default 10)
        Seed for random terms
        
    TODO: Different random coupling terms
    """
    np.random.seed(seed)
    H = np.eye(nb_spins)*U
    for ii in range(nb_spins):
        for jj in range(nb_spins):
            if ii != jj:
                H[ii, jj] = (J + delta*np.random.rand()) / np.abs(ii - jj)**float(alpha)
    return (H + H.transpose())/2


def gen_params_on_subspace(bo_args, 
                           nb_ignore = None, 
                           nb_ignore_ratio = 1):
    """
    Generates initial points on a hypersurface of the full parameter volume. E.g the first
    n parameters are set to zero, while the rest are drawn from the domain of the input dict
    TODO: update to take domain from input dict
    
    Parameters:
    ------------
    bo_args : dict
        dict containing the settings of the BO optimiser
    
    nb_ignore : int
        number of initial parameters to ignore
        
    nb_ignore_ratio : int
        ratio of init parameters that ignore the first nb_igore terms"""
    nb_params = len(bo_args['domain'])
    if nb_ignore == None:
        nb_ignore = int(nb_params/2)
    zz = nb_ignore
    ii = nb_params - nb_ignore
    init_total = bo_args['initial_design_numdata']
    init_subspace = int(nb_ignore_ratio * init_total)
    init_fullspace = init_total - init_subspace
    zeros = [[0]*zz + list(2*pi*np.random.rand(ii)) for _ in range(init_subspace)]
    full = [list(2*pi*np.random.rand(ii + zz)) for _ in range(init_fullspace)]
    return zeros + full


def _diff_between_x(X_in):
        """ Computes the euclidian distance between adjacent X values
        TODO: Might need to vectorize this in future
        
        Paramaters 
        -----
        X_in : arrave of x-vales, with new x-value of each row"""
        dX = X_in[1:] - X_in[0:-1]
        dX = [dx.dot(dx) for dx in dX]
        dX = np.sqrt(np.array(dX))
        return dX


def _round_res_dict(di_in):
    """
    Rounds the vales of the input dict. Assumes all values are "roundable"
    WORKS IN PLACE (not actually needed any more)
    
    Parameters:
    -----------
    di_in : Input dict
    """
    for key in di_in.keys():
        di_in[key] = int(np.round(di_in[key]))
    return di_in


def _all_keys(di_in, level = ''):
    """
    Prints all keys in a nested dict: Equiv to printing objs injson hierarchy"""
    for key in di_in.keys():
        print(level + str(key))
        if type(di_in[key]) == dict:
            _all_keys(di_in[key], level=level+'>')


def gen_quick_noise(readout = 0.05,
                    cnot = 0.02,
                    gate = 0.001):
    """
    Generates a quick noise model for a simulator backend. Returns 
    instance of qk.aer.noise.NoiseModel
    
    Parameters
    ------
    readout : float [0,1] (default 0.05)
        readout error probability
    cnot : float [0,1] (default 0.2)
        cnot error probability
    gate : float [0,1] (default 0.001)
        single qubit gate error probability """
    noise_model =  qk.providers.aer.noise.NoiseModel()

    
    # Error probabilities for 1 and 2 qubit gates, and readout
    gate = qk.providers.aer.noise.depolarizing_error(gate, 1)
    cnot = qk.providers.aer.noise.depolarizing_error(cnot, 2)
    readout = [[1-readout, readout], [readout, 1-readout]]
    
    # Add errors to noise model
    noise_model.add_all_qubit_quantum_error(gate, ['u1', 'u2', 'u3'])
    noise_model.add_all_qubit_quantum_error(cnot, ['cx'])
    noise_model.add_all_qubit_readout_error(readout)
    return noise_model


def gen_cyclic_graph(nb_nodes):
    """
    Returns: edges for a cyclic graph state
    
    Parameters:
    -----------
    nb_nodes : int
        number of qubits (nodes) in the cyclic graph"""
    graph = [[ii, ii+1] for ii in range(nb_nodes - 1)]
    graph.append([nb_nodes-1, 0])
    return graph


def gen_clifford_simulatable_params(circ, nb_points = 1):
    """
    Takes a qk.circuit and returns a list of clifford simulable points
    It was a waste of dam time. 

    Parameters
    ----------
    circ : qk.QuantumCircuit tupe
        Quantum circuit ideally generated by an ansatz. Assumes at least 1 parameter, 
        and that that parameters are labeled R1, R2.... etc
    nb_points : int, default 1
        The number of Clifford points you want to simulate

    Returns
    -------
    2d np.array
        Ready for BO init points. Each row is a single Clifford simulable point. 
        The ith col corresponds to the 1th parameter (R1)

    """
    
    qsam_str = circ.qasm()
    known_gates = ['rx', 'ry', 'rz', 'u2', 'u3']
    print("""Heads up: this only works for ' + ' '.join(known_gates) + ' gates \n
          And assumes parameters are labeled R1 R2.... etc""")
    def get_args(sub_str):
        params = sub_str.split(')')[0][1:]
        if ',' in params:
            return params.split(',')
        else:
            return [params]
    
    def get_args_for_gate(qsam_str, gate):
        sub_strs = qsam_str.split(gate)
        list_of_args = []
        for sub_str in sub_strs[1:]:
            list_of_args.append(get_args(sub_str))
        return list_of_args
    
    def reduce_di(di):
        kk_v = list(di.keys())
        for kk in kk_v:
            if len(di[kk]) == 0:
                di.pop(kk)
    

    di_map = {gg:get_args_for_gate(qsam_str, gg) for gg in known_gates}
    reduce_di(di_map)
    rand_clifford_points = -1*np.ones((nb_points, len(circ.parameters)))
    for kk in di_map.keys():
        for par_set in di_map[kk]:
            for pp in par_set:
                if 'R' in pp:
                    param_int = int(pp[1:])
                    if kk in 'rx ry rz':
                        val = np.random.randint(0, 2, size = nb_points)
                    elif kk in 'u2, u3':
                        val = np.random.randint(0, 5, size = nb_points) /2
                    rand_clifford_points[:,param_int] = val
                else:
                    print("Warning: there is no internal check to see if non-parameterised gates are Clifford")
    
    raise Warning("""Don't use this, it's a waste of fucking time! but I don't want to delete it yet \n
                  Use ut.eval_clifford_init instead""")
    
    return rand_clifford_points*np.pi



def eval_clifford_init(cost_obj,
                       init_points = 15,
                       seed = None):
    """
    Evaluates some initial clifford points to init a BO with easilly simulable data

    Parameters
    ----------
    cst : cost.CostAnsatz
        The cost function used to evaluate the data. Assumes rx, ry, rz parameters
    init_points : int OR array
        If int is the number of random points to calculate. Else if it's an array
        assumed to be user spesified points to int
    seed : int, optional
        Seed for random number generator of clifford points. The default is None.

    Returns : pair(X, Y)
    -------
    X : array of clifford points evaluated
    Y : Evaluation of the cost function
    
    """
    
    
    if type(init_points) == int or type(init_points) == float:
        np.random.seed(seed)
        X = np.random.randint(0, 4, size=(init_points, cost_obj.nb_params))* pi/2
    else:
        X = init_points
        
    
    simulator = qk.providers.aer.StatevectorSimulator()
    inst = qk.aqua.QuantumInstance(simulator, shots=8192, optimization_level=0)
    cost_obj.instance = inst    
    
    new_circs = gen_meas_circuits(cost_obj.ansatz.circuit, cost_obj._list_meas)
    cost_obj._meas_circuits = inst.transpile(new_circs)
    
    
    return X, cost_obj(X)
        
    
def convert_wpo_and_openfermion(operator):
    """
    Converts between openfermion qubit hamiltonians and qiskit weighted Pauli operators
    Uses dict decompositions in both cases and is full general. 
    Parameters
    ----------
    operator : openfermion hamiltonian OR qiskit wpo
        Input operator 

    Returns
    -------
    operator : openfermion hamiltonian OR qiskit wpo

    """
    def _count_qubits(openfermion_operator):
        """ Counts the number of qubits in the openfermion.operator""" 
        nb_qubits = 0
        for sett, coef in openfermion_operator.terms.items():
            if len(sett)>0:
                nb_qubits = max(nb_qubits, max([s[0] for s in sett]))
        return nb_qubits+1
                
    
    
    if str(operator.__class__) == "<class 'openfermion.ops._qubit_operator.QubitOperator'>":
        nb_qubits = _count_qubits(operator)

        iden = qk.quantum_info.Pauli.from_label('I'*nb_qubits)
        offset = operator.terms[()]
        qiskit_operator = WeightedPauliOperator([(offset, iden)])
        for sett, coef in operator.terms.items():
            new_sett = 'I'*nb_qubits
            for s in sett:
                new_sett = new_sett[:(s[0])] + s[1] + new_sett[(s[0]+1):]
            pauli = qk.quantum_info.Pauli.from_label(new_sett)
            op = WeightedPauliOperator([(coef, pauli)])
            # print(coef)
            # print(new_sett)
            qiskit_operator = qiskit_operator + op
        return qiskit_operator    
    else:
        raise NotImplementedError("Currently only converts 1 way, openfermion-> qiskit wpo")
        

def convert_to_settings_and_weights(operator):
    """
    Converts a qiskit, or openfermion qubit operator to a list of weights and settings

    Parameters
    ----------
    operator : operator to convert
        input operator

    Returns
    -------
    weights : list
        ordered list of (potentially complex) numbers that are the measurement weights for each setting
    settings : TYPE
        List of measurment settings in string format 'xx1xyz' etc.
    """
    if str(operator.__class__) == "<class 'qiskit.aqua.operators.legacy.weighted_pauli_operator.WeightedPauliOperator'>":
        all_ops = operator.to_dict()['paulis']
        weights = []
        settings = []
        for ops in all_ops:
            ww = ops['coeff']['real'] + 1j* ops['coeff']['imag']
            settings.append(ops['label'].lower().replace('i','1'))
            weights.append(ww)
        if max([w.imag for w in weights]) - min([w.imag for w in weights]) == 0:
            weights = [w.real for w in weights]
        return weights, settings