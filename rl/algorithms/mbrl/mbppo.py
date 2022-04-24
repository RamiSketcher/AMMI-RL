import os, subprocess, sys
import argparse
import importlib
import datetime
import random

import time
import wandb

import numpy as np
import torch as T
import torch.nn.functional as F

# T.multiprocessing.set_sharing_strategy('file_system')

from rl.algorithms.mbrl.mbrl import MBRL
from rl.algorithms.mfrl.ppo import PPO
from rl.world_models.fake_world import FakeWorld
import rl.environments.mbpo.static as mbpo_static
# from rl.data.dataset import RLDataModule





class MBPPO(MBRL, PPO):
    """
    Greek alphabet:
        Α α, Β β, Γ γ, Δ δ, Ε ε, Ζ ζ, Η η, Θ θ, Ι ι, Κ κ, Λ λ, Μ μ,
        Ν ν, Ξ ξ, Ο ο, Π π, Ρ ρ, Σ σ/ς, Τ τ, Υ υ, Φ φ, Χ χ, Ψ ψ, Ω ω.

    Algorithm: Model-Based Game: Policy As Leader (PAL) – Practical Version

        01: Initialize: Models parameters( Policy net πφ, Value net Vψ, ensemble of MDP world models {M^θ}_{1:nM} )
        02. Initialize: Replay buffer D.
        03: Hyperparameters: Initial samples Ninit, samples per update N, buffer size B ≈ N, number of NPG steps K ≈ 1
        04: Initial Data: Collect N_init samples from the environment by interacting with initial policy. Store data in buffer D.
        05: for k = 0, 1, 2, ... do
        06:    Learn dynamics model(s) Mkat_k+1 using data in the buffer.
        07:    Policy updates: π_k+1; V_k+1 = MB-PPO(π_k, V_k, Mhat_k+1) // call K times
        08:    Collect dataset of N samples from World by interacting with πk+1.
        09.    Add data to replay buffer D, discarding old data if size is larger than B.
        10: end for


    Algorithm: Model-Based Game: Model As Leader (MAL) – Practical Version
        1: Initialize: Policy network π_0, model network(s) Mhat_0, value network V_0.
        2: Hyperparameters: Initial samples N_init, samples per update N, number of PPO steps K >> 1
        3: Initial Data: Collect N_init samples from the environment by interacting with initial policy. Store data in buffer D.
        4: Initial Model: Learn model(s) Mhat_0 using data in D.
        5: for k = 0, 1, 2, ... do
        6:    Optimize π_k+1 using Mck by running K >> 1 steps of model-based PPO (Subroutine 1).
        7:    Collect dataset D_k+1 of N samples from world using πk+1. Aggregate data D = D U D_k+1.
        8:    Learn dynamics model(s) Mhat_k+1 using data in D.
        9: end for


    Algorithm: Model-Based Proximal Policy Optimization (On-Policy, Dyna-style, Model-Based)

        01. Inputs: Models parameters( Policy net πφ, Value net Vψ, ensemble of MDP world models {M^θ}_{1:nM}, Replay buffer D)
        02. Initialize: Trajectory buffer Dτ = {}
        03. Hyperparameters: Disc. factor γ, GAE λ, num traj's Nτ, model rollout horizon H
        04. for n = 0, 1, 2, ..., N:
        05.     Collect set of traj's {τ^πk} by πk = π(φk) for e = 0, 1, 2, ..., E
        06.     Aggregate the traj's in traj buffer, Dτ = Dτ U {τ^πk}
        07.     Compute RTG R^_t, GAE A^_t based on Vk = V(θk)
        08.     for g = 0, 1, 2, ..., G do
        09.         Update πφ by maxz Jπ
                        φ = arg max_φ {(1/T|Dk|) sum sum min((π/πk), 1 +- eps) Aπk }
        10.         Fit Vθ by MSE(Jv)
                        θ = arg min_θ {(1/T|Dk|) sum sum (Vθ(st) - RTG)^2 }
        11.     end for
        12. end for
        1x. Return: Policy net πθ, value net Vφ

    Subroutine 1: Model-Based Natural Policy Gradient Update Step
        1: Require: Policy (stochastic) network πθ, value/baseline network V , ensemble of MDP dynamics models fMcφg,
        reward function R, initial state distribution or buffer.
        2: Hyperparameters: Discount factor γ, GAE λ, number of trajectories Nτ, rollout horizon H, normalized NPG step
        size δ
        3: Initialize trajectory buffer Dτ = fg
        4: for k = 1; 2; : : : ; Nτ do
        5: Sample initial state sk 0 from initial state distribution/buffer
        6: Perform H step rollout from sk 0 with πθ to get τjk = (sk 0; ak 0; sk 1; ak 2; : : : sk H; ak H), one for each model Mcφj in the
        ensemble.
        7: Query reward function to obtain rewards for each step of the trajectories
        8: Truncate trajectories if termination/truncation conditions are part of the environment
        9: Aggregate the trajectories in trajectory buffer, Dτ = Dτ [ fτg
        10: end for
        11: Compute advantages for each trajectory using V and GAE (Schulman et al., 2016).
        12: Compute vanilla policy gradient using the dataset
        g = E(s;a)∼Dτ [rθ log πθ(ajs)Aπ(s; a)]
        13: Perform normalized NPG update (F denotes the Fisher matrix)
        θ = θ + sgT Fδ−1g F −1g
        14: Update value/baseline network V to fit the computed returns in Dτ.
        15: Return Policy network πθ, value network V

    """
    def __init__(self, exp_prefix, configs, seed, device, wb) -> None:
        super(MBPPO, self).__init__(exp_prefix, configs, seed, device)
        # print('init MBPPO Algorithm!')
        self.configs = configs
        self.seed = seed
        self._device_ = device
        self.WandB = wb
        self._build()


    ## build MEMB components: (env, D, AC, alpha)
    def _build(self):
        super(MBPPO, self)._build()
        self._set_ppo()
        self._set_fake_world()


    ## SAC
    def _set_ppo(self):
        PPO._build_ppo(self)


    ## FakeEnv
    def _set_fake_world(self):
        env_name = self.configs['environment']['name']
        device = self._device_
        if self.configs['environment']['name'][:4] == 'pddm':
        	static_fns = None
        else:
        	static_fns = mbpo_static[env_name[:-3].lower()]

        # self.fake_world = FakeWorld(self.world_model, static_fns, env_name, self.learn_env, self.configs, device)
        self.fake_world = FakeWorld(self.world_model)


    def learn(self):
        N = self.configs['algorithm']['learning']['epochs']
        NT = self.configs['algorithm']['learning']['epoch_steps']
        Ni = self.configs['algorithm']['learning']['init_epochs']
        Nx = self.configs['algorithm']['learning']['expl_epochs']

        E = self.configs['algorithm']['learning']['env_steps']
        G_sac = self.configs['algorithm']['learning']['grad_SAC_steps']

        # batch_size = self.configs['data']['batch_size']

        model_train_frequency = self.configs['world_model']['model_train_freq']
        batch_size_m = self.configs['world_model']['network']['batch_size'] # bs_m
        wm_epochs = self.configs['algorithm']['learning']['grad_WM_steps']
        real_ratio = self.configs['data']['real_ratio'] # rr
        batch_size = self.configs['data']['batch_size'] # bs
        batch_size_ro = self.configs['data']['rollout_batch_size'] # bs_ro

        o, Z, el, t = self.learn_env.reset(), 0, 0, 0
        # o, Z, el, t = self.initialize_learning(NT, Ni)
        # oldJs = [0, 0, 0]
        # JQList, JAlphaList, JPiList = [0], [0], [0]
        # AlphaList = [self.alpha]*Ni

        # JTrainList, JValList, LossTestList = [0], [0], [0]
        # WMList = {'mu': [0]*Ni, 'sigma': [0]*Ni}
        # JMeanTrainList, JTrainList, JMeanValList, JValList = [], [], [], []
        # LossTestList = []
        # WMList = {'mu': [], 'sigma': []}

        logs = dict()
        lastEZ, lastES = 0, -2
        K = 1

        start_time_real = time.time()
        for n in range(1, N+1):
            if self.configs['experiment']['print_logs']:
                print('=' * 50)
                if n > Nx:
                    print(f'\n[ Epoch {n}   Learning ]'+(' '*50))
                    # JQList, JPiList = [], []
                    # JTrainList, JValList, LossTestList = [], [], []
                    oldJs = [0, 0, 0]
                    JQList, JAlphaList, JPiList = [0], [0], [0]
                    JTrainList, JValList, LossTestList = [0], [0], [0]
                elif n > Ni:
                    print(f'\n[ Epoch {n}   Exploration + Learning ]'+(' '*50))
                    JQList, JPiList = [], []
                    JTrainList, JValList, LossTestList = [], [], []
                else:
                    print(f'\n[ Epoch {n}   Inintial Exploration ]'+(' '*50))
                    oldJs = [0, 0, 0]
                    JQList, JAlphaList, JPiList = [0], [0], [0]
                    JTrainList, JValList, LossTestList = [0], [0], [0]

            print(f'[ Replay Buffer ] Size: {self.env_buffer.size}')
            nt = 0
            learn_start_real = time.time()
            while nt < NT: # full epoch
                # Interaction steps
                for e in range(1, E+1):
                    # o, Z, el, t = self.internact(n, o, Z, el, t)
                    o, d, Z, el, t = self.internact_op(n, o, d, Z, el, t)

                # Taking gradient steps after exploration
                if n > Ni:
                    if nt % model_train_frequency == 0:
                        #03. Train model pθ on Denv via maximum likelihood
                        # PyTorch Lightning Model Training
                        print(f'\n[ Epoch {n}   Training World Model ]'+(' '*50))
                        # print(f'\n\n[ Training ] Dynamics Model(s), mEpochs = {mEpochs}
                        # self.data_module = RLDataModule(self.env_buffer, self.configs['data'])

                        # JTrainLog, JValLog, LossTest = self.fake_world.train(self.data_module)
                        # JTrainList.append(JTrainLog)
                        # JValList.append(JValLog)
                        # LossTestList.append(LossTest)

                        ho_mean = self.fake_world.train_fake_world(self.env_buffer)
                        JValList.append(ho_mean) # ho: holdout

                        # Update K-steps length
                        K = self.set_rollout_length(n)

                        # Reallocate model buffer
                        # if K != K_new:
                        #     K = K_new
                        self.reallocate_model_buffer(batch_size_ro, K, NT, model_train_frequency)

                        # Generate M k-steps imaginary rollouts for SAC traingin
                        self.rollout_world_model(batch_size_ro, K, n)

                    # JQList, JPiList = [], []
                    # AlphaList = [self.alpha]*G_sac
                    with T.no_grad(): v = self.actor_critic.get_v(T.Tensor(o))
                    self.buffer.traj_tail(d, v)
                    # Optimizing policy and value networks
                    b_inds = np.arange(batch_size)
                    for g in range(1, G_sac+1): # it was "for g in (1, G_sac+1):" for 2 months, and I did't know!! ;(
                        # print(f'Actor-Critic Grads...{g}', end='\r')
                        print(f'[ Epoch {n}   Training Actor-Critic ] Env Steps: {nt+1} | AC Grads: {g} | Return: {round(Z, 2)}', end='\r')
                        for b in range(0, batch_size, mini_batch_size):
                            # print('ptr: ', self.buffer.ptr)
                            mini_batch = self.ppo_batch(real_ratio, batch_size)
                            Jv, Jpi, stop_pi = self.trainAC(g, mini_batch, oldJs)
                            oldJs = [Jv, Jpi]
                            JVList.append(Jv.item())
                            JPiList.append(Jpi.item())

                nt += E

            print('\n')
            # logs['time/training                  '] = time.time() - learn_start_real

            # logs['training/wm/Jtrain_mean        '] = np.mean(JMeanTrainList)
            # logs['training/wm/Jtrain             '] = np.mean(JTrainList)
            logs['training/wm/Jval               '] = np.mean(JValList)
            # logs['training/wm/test_mse           '] = np.mean(LossTestList)

            logs['training/ppo/Jq                '] = np.mean(JVList)
            logs['training/ppo/Jpi               '] = np.mean(JPiList)

            logs['data/env_buffer                '] = self.env_buffer.size
            if hasattr(self, 'model_buffer'):
                logs['data/model_buffer              '] = self.model_buffer.size
            else:
                logs['data/model_buffer              '] = 0
            logs['data/rollout_length            '] = K

            eval_start_real = time.time()
            EZ, ES, EL = self.evaluate_op()

            # logs['time/evaluation                '] = time.time() - eval_start_real

            if self.configs['environment']['type'] == 'mujoco-pddm-shadowhand':
                logs['evaluation/episodic_score_mean '] = np.mean(ES)
                logs['evaluation/episodic_score_std  '] = np.std(ES)
            else:
                logs['evaluation/episodic_return_mean'] = np.mean(EZ)
                logs['evaluation/episodic_return_std '] = np.std(EZ)
            logs['evaluation/episodic_length_mean'] = np.mean(EL)

            logs['time/total                     '] = time.time() - start_time_real

            # if n > (N - 50):
            #     if self.configs['environment']['type'] == 'mujoco-pddm-shadowhand':
            #         if np.mean(ES) > lastES:
            #             print(f'[ Epoch {n}   Agent Saving ]                    ')
            #             env_name = self.configs['environment']['name']
            #             alg_name = self.configs['algorithm']['name']
            #             T.save(self.actor_critic.actor,
            #             f'./saved_agents/{env_name}-{alg_name}-seed:{self.seed}-epoch:{n}.pTtar')
            #             lastES = np.mean(ES)
            #     else:
            #         if np.mean(EZ) > lastEZ:
            #             print(f'[ Epoch {n}   Agent Saving ]                    ')
            #             env_name = self.configs['environment']['name']
            #             alg_name = self.configs['algorithm']['name']
            #             T.save(self.actor_critic.actor,
            #             f'./saved_agents/{env_name}-{alg_name}-seed:{self.seed}-epoch:{n}.pTtar')
            #             lastEZ = np.mean(EZ)

            # Printing logs
            if self.configs['experiment']['print_logs']:
                for k, v in logs.items():
                    print(f'{k}  {round(v, 2)}')

            # WandB
            if self.WandB:
                wandb.log(logs)

        self.learn_env.close()
        self.eval_env.close()


    def set_rollout_length(self, n):
        if self.configs['world_model']['rollout_schedule'] == None:
        	K = 1
        else:
        	min_epoch, max_epoch, min_length, max_length = self.configs['world_model']['rollout_schedule']

        	if n <= min_epoch:
        		K = min_length
        	else:
        		dx = (n - min_epoch) / (max_epoch - min_epoch)
        		dx = min(dx, 1)
        		K = dx * (max_length - min_length) + min_length

        K = int(K)
        return K


    def rollout_world_model(self, batch_size_ro, K, n):
    	#07. Sample st uniformly from Denv
    	device = self._device_
    	batch_size = min(batch_size_ro, self.env_buffer.size)
    	print(f'[ Epoch {n}   Model Rollout ] Batch Size: {batch_size} | Rollout Length: {K}'+(' '*50))
    	B_ro = self.env_buffer.sample_batch_np(batch_size)
    	O = B_ro['observations'] # Torch
    	# print('rollout_world_model, O.shape: ', O.shape)
    	# print('a.ptr=', self.model_buffer.ptr)

    	#08. Perform k-step model rollout starting from st using policy πφ; add to Dmodel
    	for k in range(1, K+1):
    		with T.no_grad():
    			# A, _ = self.actor_critic.actor(O) # ip:Tensor, op:Tensor
    			A, _ = self.actor_critic.actor.step_np(T.as_tensor(O, dtype=T.float32)) # ip:Tensor, op:Numpy

    		# O_next, R, D, _ = self.fake_world.step(O, A) # ip:Tensor, op:Tensor
    		# O_next, R, D, _ = self.fake_world.step_np(O, A) # ip:Tensor, op:Numpy
    		O_next, R, D, _ = self.fake_world.step(O, A) # ip:Tensor, op:Numpy

    		# print('rollout_world_model, O_next.shape: ', O_next.shape)

    		# O = O.detach().cpu().numpy()
    		# A = A.detach().cpu().numpy()

    		# self.model_buffer.store_batch(O.numpy(), A, R, O_next, D) # ip:Numpy
    		self.model_buffer.store_batch(O, A, R, O_next, D) # ip:Numpy
    		# print('model buff ptr: ', self.model_buffer.ptr)

    		# nonD = ~D
    		nonD = ~D.squeeze(-1)
    		if nonD.sum() == 0:
    		    print(f'[ Epoch {n}   Model Rollout ] Breaking early: {k} | {nonD.sum()} / {nonD.shape}')
    		    break

    		O = O_next[nonD]#.reshape(-1,len(O[0,:]))
    		# O = T.as_tensor(O, dtype=T.float32)#.to(device)

    	# print('z.ptr=', self.model_buffer.ptr)


    def ppo_batch(self, real_ratio, batch_size):
    	batch_size_real = int(real_ratio * batch_size) # 0.05*256
    	batch_size_img = batch_size - batch_size_real # 256 - (0.05*256)
    	B_real = self.env_buffer.sample_batch(batch_size_real, self._device_)

    	if batch_size_img > 0:
    		B_img = self.model_buffer.sample_batch(batch_size_img, self._device_)
    		keys = B_real.keys()
    		B = {k: T.cat((B_real[k], B_img[k]), dim=0) for k in keys}
    	else:
    		B = B_real
    	return B





def main(exp_prefix, config, seed, device, wb):

    print('Start an MBPPO experiment...')
    print('\n')

    configs = config.configurations

    if seed:
        random.seed(seed), np.random.seed(seed), T.manual_seed(seed)

    alg_name = configs['algorithm']['name']
    env_name = configs['environment']['name']
    env_type = configs['environment']['type']
    wm_epochs = configs['algorithm']['learning']['grad_WM_steps']
    DE = configs['world_model']['num_ensembles']

    group_name = f"{env_name}-{alg_name}-A"
    exp_prefix = f"seed:{seed}"

    if wb:
        # print('WandB')
        wandb.init(
            name=exp_prefix,
            group=group_name,
            # project='test',
            project='AMMI-RL-2022',
            config=configs
        )

    agent = MBPPO(exp_prefix, configs, seed, device, wb)

    agent.learn()

    print('\n')
    print('... End the MBPPO experiment')


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument('-exp_prefix', type=str)
    parser.add_argument('-cfg', type=str)
    parser.add_argument('-seed', type=str)
    parser.add_argument('-device', type=str)
    parser.add_argument('-wb', type=str)

    args = parser.parse_args()

    exp_prefix = args.exp_prefix
    sys.path.append(f"{os.getcwd()}/configs")
    config = importlib.import_module(args.cfg)
    seed = int(args.seed)
    device = args.device
    wb = eval(args.wb)

    main(exp_prefix, config, seed, device, wb)
