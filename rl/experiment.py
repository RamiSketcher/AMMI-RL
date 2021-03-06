import os, subprocess, sys
import argparse
import importlib
import datetime
import random

import torch as T
# T.multiprocessing.set_sharing_strategy('file_system')

import wandb

# from rl.mfrl.sac import SAC

import warnings
warnings.filterwarnings('ignore')





def main(cfg, seed, device, wb):
    print('\n')
    sys.path.append("./configs")
    # print('cfg: ', cfg)
    config = importlib.import_module(cfg)
    # print('config: ', config)
    configurations = config.configurations

    alg_name = configurations['algorithm']['name']
    env_name = configurations['environment']['name']
    env_type = configurations['environment']['type']

    group_name = f"iii-{env_type}-{env_name}"
    # now = datetime.datetime.now()
    # exp_prefix = f"{group_name}-{seed}--[{now.year}-{now.month}-{now.day}]-->{now.hour}:{now.minute}:{now.second}"
    exp_prefix = f"{group_name}-{alg_name}-seed:{seed}"

    print('=' * 50)
    print(f'Starting an RL experiment')
    print(f"\t Algorithm:   {alg_name}")
    print(f"\t Environment: {env_name}")
    print(f"\t Random seed: {seed}")
    print('=' * 50)

    print('Configurations:\n', configurations)

    # configs['seed'] = seed

    # if configurations['experiment']['WandB']:
    #     # print('WandB')
    #     wandb.init(
    #         name=exp_prefix,
    #         group=group_name,
    #         # project='test',
    #         project='AMMI-RL-2022',
    #         config=configurations
    #     )

    cwd = os.getcwd()
    alg_dir = cwd + f'/algorithms/'


    for root, dirs, files in os.walk(alg_dir):
        for f in files:
            if f == (alg_name.lower() + '.py'):
                alg = os.path.join(root, f)
    # print('alg', alg)

    subprocess.run(['python', alg,
                    '-exp_prefix', exp_prefix,
                    '-cfg', cfg,
                    '-seed', str(seed),
                    '-device', device,
                    '-wb', str(wb) ])

    # T.save(agent.actor_critic.actor,
    # f'./agents/agent-{env_name}-{alg_name}-seed:{seed}.pth.tar')

    print('\n')
    print('End of the RL experiment')
    print('=' * 50)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument('-cfg', type=str)
    parser.add_argument('-seed', type=int, default=0)
    parser.add_argument('-device', type=str, default='cpu')
    # parser.add_argument('-gpu', type=str, nargs='?', default=False, const=True)
    parser.add_argument('-wb', action='store_true')

    args = parser.parse_args()


    cfg = args.cfg
    seed = args.seed
    # device = 'cuda' if args.gpu else 'cpu'
    device = args.device
    wb = args.wb


    main(cfg, seed, device, wb)
