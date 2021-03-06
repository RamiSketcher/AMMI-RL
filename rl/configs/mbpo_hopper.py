

configurations = {

    'environment': {
            'name': 'Hopper-v2',
            'type': 'gym-mujoco',
            'state_space': 'continuous',
            'action_space': 'continuous',
            'horizon': 1e3,
        },

    'algorithm': {
        'name': 'MBPO',
        'model-based': True,
        'on-policy': False,
        'learning': {
            'epochs': 500, # N epochs
            'epoch_steps': 1000, # NT steps/epoch
            'init_epochs': 5, # Ni epochs = 5000 exploration steps
            'expl_epochs': 5, # Nx epochs
            # 'real_epochs': 0, # Nr epochs

            'env_steps' : 1, # E: interact E times then train
            'grad_WM_steps': 0, # G: ac grad
            'grad_SAC_steps': 20, #20, # ACG: ac grad, 40

            'policy_update_interval': 1,
            'alpha_update_interval': 1,
            'target_update_interval': 1,


            'n_episodes_rollout': -1,

            'use_sde': False,
            'sde_sample_freq': -1,
            'use_sde_at_warmup': False,
                    },

        'evaluation': {
            'evaluate': True,
            'eval_deterministic': True,
            'eval_freq': 1, # Evaluate every 'eval_freq' epochs --> Ef
            'eval_episodes': 5, # Test policy for 'eval_episodes' times --> EE
            'eval_render_mode': None,
        }
    },


    'world_model': {
        'type': 'PE',
        'num_ensembles': 7, # 7
        'num_elites': 5, # 5
        'sample_type': 'Random',
        'learn_reward': True,
        # 'learn_log_sigma_limits': False,
        'oq_model_train_freq': 250,#250, # Mf
        'model_retain_epochs': 1,
        'oq_rollout_schedule': [20, 150, 1, 15], # original
        'network': {
            'arch': [200, 200, 200, 200], #@#
            'init_weights': 3e-3,
            'init_biases': 0,
            'activation': 'SiLU',
            'output_activation': 'nn.Identity',
            'optimizer': "Adam", #@#
            'lr': 1e-3, #@#
            'wd': 1e-5,
            'eps': 1e-8,
            'dropout': None,
            'batch_size': 256,
            # 'device': "auto",
        }
    },


    'actor': {
        'type': 'gaussianpolicy',
        'action_noise': None,
        'alpha': 0.2, # Temprature/Entropy #@#
        'automatic_entropy': False,
        'target_entropy': 'auto',
        'network': {
            # 'arch': [128, 128],
            'arch': [256, 256],
            # 'activation': 'Tanh',
            'activation': 'PReLU',
            'output_activation': 'nn.Identity',
            'initialize_weights': True,
            'optimizer': "Adam",
            'lr': 3e-4,
        }
    },


    'critic': {
        'type': 'sofQ',
        'number': 2,
        'gamma': 0.99,
        # 'gamma': 0.995,
        'tau': 5e-3,
        'network': {
            # 'arch': [128, 128],
            # 'arch': [256, 128],
            'arch': [256, 256],
            # 'activation': 'Tanh',
            'activation': 'PReLU',
            'output_activation': 'nn.Identity',
            'initialize_weights': True,
            'optimizer': "Adam",
            # 'lr': 1e-3, # Conv at Ep:?
            'lr': 3e-4, # Conv at Ep:340 | ReLU-16
        }
    },


    'data': {
        'buffer_type': 'simple',
        'optimize_memory_usage': False,
        'buffer_size': int(5e5),
        'model_buffer_size': int(1e7),
        'real_ratio': 0.05,
        'model_val_ratio': 0.2,
        'oq_rollout_batch_size': int(1e5),
        'model_batch_size': 256,
        'batch_size': 256,
    },


    'experiment': {
        'verbose': 0,
        'print_logs': True,
    }
}
