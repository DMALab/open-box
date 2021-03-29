import time
import os
import numpy as np
import pickle as pkl
from litebo.utils.logging_utils import get_logger, setup_logger
from litebo.core.message_queue.master_messager import MasterMessager

PLOT = False
try:
    import matplotlib.pyplot as plt
    plt.switch_backend('agg')
    PLOT = True
except Exception as e:
    pass


class async_mqBaseFacade(object):
    def __init__(self, objective_func,
                 restart_needed=False,
                 need_lc=False,
                 method_name='default_method_name',
                 log_directory='logs',
                 data_directory='data',
                 time_limit_per_trial=600,
                 runtime_limit=None,
                 max_queue_len=300,
                 ip='',
                 port=13579,
                 authkey=b'abc',):
        self.log_directory = log_directory
        if not os.path.exists(self.log_directory):
            os.makedirs(self.log_directory)
        self.data_directory = data_directory
        if not os.path.exists(self.data_directory):
            os.makedirs(self.data_directory)

        self.logger = self._get_logger(method_name)

        self.objective_func = objective_func
        self.trial_statistics = []
        self.recorder = []

        self.global_start_time = time.time()
        self.runtime_limit = None
        self._history = {"time_elapsed": [], "performance": [], "best_trial_id": [], "configuration": []}
        self.global_incumbent = 1e10
        self.global_incumbent_configuration = None
        self.global_trial_counter = 0
        self.restart_needed = restart_needed
        self.record_lc = need_lc
        self.method_name = method_name
        # evaluation metrics
        self.stage_id = 1
        self.stage_history = {'stage_id': [], 'performance': []}
        self.grid_search_perf = []

        if self.method_name is None:
            raise ValueError('Method name must be specified! NOT NONE.')

        self.time_limit_per_trial = time_limit_per_trial
        self.runtime_limit = runtime_limit
        assert self.runtime_limit is not None

        max_queue_len = max(300, max_queue_len)
        self.master_messager = MasterMessager(ip, port, authkey, max_queue_len, max_queue_len)

    def set_restart(self):
        self.restart_needed = True

    def set_method_name(self, name):
        self.method_name = name

    def add_stage_history(self, stage_id, performance):
        self.stage_history['stage_id'].append(stage_id)
        self.stage_history['performance'].append(performance)

    def add_history(self, time_elapsed, performance, trial_id, config):
        self._history['time_elapsed'].append(time_elapsed)
        self._history['performance'].append(performance)
        self._history['best_trial_id'].append(trial_id)
        self._history['configuration'].append(config)

    def run(self):
        try:
            worker_num = 0
            while True:
                if self.runtime_limit is not None and time.time() - self.global_start_time > self.runtime_limit:
                    self.logger.info('Runtime budget meets!')
                    return

                # Get observation from worker
                observation = self.master_messager.receive_message()  # return_info, time_taken, trial_id, config
                if observation is None:
                    # Wait for workers.
                    # self.logger.info("Master: wait for worker results. sleep 1s.")
                    time.sleep(1)
                    continue

                return_info, time_taken, trial_id, config = observation
                # worker init
                if config is None:
                    worker_num += 1
                    self.logger.info("Worker %d init." % (worker_num, ))
                # update observation
                else:
                    global_time = time.time() - self.global_start_time
                    self.logger.info('Master get observation: %s. Global time=%.2fs.' % (str(observation), global_time))
                    n_iteration = return_info['n_iteration']
                    perf = return_info['loss']
                    t = time.time()
                    self.update_observation(config, perf, n_iteration)
                    self.logger.info('update_observation() cost %.2fs.' % (time.time() - t,))
                    self.recorder.append({'trial_id': trial_id, 'time_consumed': time_taken,
                                          'configuration': config, 'n_iteration': n_iteration,
                                          'return_info': return_info, 'global_time': global_time})

                # Send new job
                t = time.time()
                config, n_iteration, extra_conf = self.get_job()
                self.logger.info('get_job() cost %.2fs.' % (time.time()-t, ))
                msg = [config, extra_conf, self.time_limit_per_trial, n_iteration, self.global_trial_counter]
                self.master_messager.send_message(msg)
                self.global_trial_counter += 1
                self.logger.info('Master send job: %s.' % (msg,))

        except Exception as e:
            print(e)
            self.logger.error(str(e))

    def get_job(self):
        raise NotImplementedError

    def update_observation(self, config, perf, n_iteration):
        raise NotImplementedError

    def save_intemediate_statistics(self, save_stage=False):
        # file_name = '%s.npy' % self.method_name
        # x = np.array(self._history['time_elapsed'])
        # y = np.array(self._history['performance'])
        # np.save(os.path.join(self.data_directory, file_name), np.array([x, y]))
        #
        # config_file_name = 'config_%s.pkl' % self.method_name
        # with open(os.path.join(self.data_directory, config_file_name), 'wb') as f:
        #     pkl.dump(self.global_incumbent_configuration, f)
        #
        # record_file_name = 'record_%s.pkl' % self.method_name
        # with open(os.path.join(self.data_directory, record_file_name), 'wb') as f:
        #     pkl.dump(self.recorder, f)
        #
        # if save_stage:
        #     stage_file_name = 'stage_%s.npy' % self.method_name
        #     stage_x = np.array(self.stage_history['stage_id'])
        #     stage_y = np.array(self.stage_history['performance'])
        #     np.save(os.path.join(self.data_directory, stage_file_name), np.array([stage_x, stage_y]))
        #
        # if PLOT:
        #     plt.plot(x, y)
        #     plt.xlabel('Time elapsed (sec)')
        #     plt.ylabel('Validation error')
        #     plt.savefig("data/%s.png" % self.method_name)
        return

    def _get_logger(self, name):
        logger_name = name
        setup_logger(os.path.join(self.log_directory, '%s.log' % str(logger_name)), None)
        return get_logger(self.__class__.__name__)
