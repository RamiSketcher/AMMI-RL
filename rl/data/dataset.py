# import random
from typing import Type, List, Tuple, Optional

# import numpy as np
import torch as T
from torch.utils.data import random_split, DataLoader
from torch.utils.data.dataset import Dataset, IterableDataset
# T.multiprocessing.set_sharing_strategy('file_system')

from pytorch_lightning import LightningDataModule




class RLDataset_iter(IterableDataset): # Take env_buffer, return all samples in a Dataset

    def __init__(self, env_buffer):
        super(RLDataset, self).__init__()
        # print('init RLDataset!')
        self.buffer = env_buffer

    def __len__(self):
        return self.buffer.size

    def __iter__(self):
        data = self.buffer.return_all()

        Os = data['observations']
        As = data['actions']
        Rs = data['rewards']
        Os_next = data['observations_next']
        Ds = data['terminals']

        for i in range(len(Ds)):
        	yield Os[i], As[i], Rs[i], Os_next[i], Ds[i]



class RLDataset(Dataset): # Take env_buffer, return all samples in a Dataset

    def __init__(self, env_buffer):
        super(RLDataset, self).__init__()
        # print('init RLDataset!')
        self.buffer = env_buffer
        self.k = 1

    def __len__(self):
        return self.buffer.size

    def __getitem__(self, idx):
        # print(f'RLDataset.__getitem__={self.k}')
        # self.k += 1
        # if T.is_tensor(idx):
        #     idx = idx.tolist()
        # buffer = self.buffer.return_all_np()
        #
        # data = buffer
        # # print('RLDataset: Os shape', data['observations'].shape)
        #
        # Os = data['observations'][idx]
        # # print('RLDataset: Os[idx] shape', Os.shape)
        # As = data['actions'][idx]
        # Rs = data['rewards'][idx]
        # Os_next = data['observations_next'][idx]
        # Ds = data['terminals'][idx]

        # Os = np.array(data['observations'][idx])
        # print('RLDataset: Os', type(Os))
        # As = np.array(data['actions'][idx])
        # Rs = np.array(data['rewards'][idx])
        # Os_next = np.array(data['observations_next'][idx])
        # Ds = np.array(data['terminals'][idx])

        # return Os, As, Rs, Os_next, Ds


        o = self.buffer.obs_buf[idx]
        a = self.buffer.act_buf[idx]
        r = self.buffer.rew_buf[idx]
        o_next = self.buffer.obs_next_buf[idx]
        d = self.buffer.ter_buf[idx]

        return o, a, r, o_next, d


class RLDataModule(LightningDataModule):

    def __init__(self, data_buffer, configs):
        super(RLDataModule, self).__init__()
        # print('init RLDataModule!')
        self.data_buffer = data_buffer
        self.configs = configs
        self.i = 1
        self.j = 1
        self.d = 1

    # def setup(self, stage: Optional[str] = None):
    #     print(f'RLDataModule.setup={self.i}')
    #     self.i +=1
    #
    #     val_ratio = self.configs['model_val_ratio']
    #     rl_dataset = RLDataset(self.data_buffer) # Take env_buffer & sample all data
    #
    #     if stage == "fit" or stage is None:
    #         # print(f'stage=fit={self.s}')
    #         # self.s += 1
    #         # print('stage == fit')
    #         # rl_dataset = RLDataset(self.data_buffer) # Take env_buffer & sample all data
    #         val = int(val_ratio*len(rl_dataset))
    #         train = len(rl_dataset) - val
    #         self.train_set, self.val_set = random_split(rl_dataset, [train, val])
    #         # self.train_set = rl_dataset


    def update_dataset(self):
        # print(f'RLDataModule.update_dataset={self.d}')
        # self.d +=1

        val_ratio = self.configs['model_val_ratio']
        rl_dataset = RLDataset(self.data_buffer) # Take env_buffer & sample all data
        val = int(val_ratio*len(rl_dataset))
        train = len(rl_dataset) - val
        self.train_set, self.val_set = random_split(rl_dataset, [train, val])


    def train_dataloader(self): # called once at "fit" time
        # print('train_dataloader')
        batch_size = self.configs['model_batch_size']
        train_loader = DataLoader(dataset=self.train_set,
        						  batch_size=batch_size,
            					  shuffle=False,
        						  # num_workers=4, # Calls X RLDataset.__iter__() times
        						  # pin_memory=True
        						  )
        return train_loader


    def val_dataloader(self):
        # print('val_dataloader')
        batch_size = self.configs['model_batch_size']
        val_loader = DataLoader(dataset=self.val_set,
                                batch_size=batch_size,
                                shuffle=False,
                                # num_workers=4, # Calls X RLDataset.__iter__() times
                                # pin_memory=True
        						  )
        return val_loader