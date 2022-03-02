# TODO: model
import random
import copy
import typing

import warnings
warnings.filterwarnings('ignore')

# import logging
# logging.getLogger('lightning').setLevel(0)

import numpy as np
from numpy.random.mtrand import normal
import torch as T
from torch._C import dtype
from torch.distributions.normal import Normal
nn = T.nn
F = nn.functional
from torch.utils.data import DataLoader
from torch.utils.data.dataset import IterableDataset
# T.multiprocessing.set_sharing_strategy('file_system')

import pytorch_lightning as pl
from pytorch_lightning import LightningModule, Trainer
from pytorch_lightning.callbacks.early_stopping import EarlyStopping

from rl.networks.mlp import MLPNet



LOG_SIGMA_MAX = 2
LOG_SIGMA_MIN = -20

epsilon = 1e-8







def init_weights_(l):
    """
    source: https://github.com/Xingyu-Lin/mbpo_pytorch/blob/main/model.py#L64
    """

    def truncated_normal_(w, mean=0.0, std=1.0):
        nn.init.normal_(w, mean=mean, std=std)
        while True:
            i = T.logical_or(w < mean - 2*std, w > mean + 2*std)
            bound = T.sum(i).item()
            if bound == 0: break
            w[i] = T.normal(mean, std, size=(bound, ), device=w.device)
        return w

    if isinstance(l, nn.Linear):
        ip_dim = l.weight.data.shape[0]
        std = 1 / (2 * np.sqrt(ip_dim))
        truncated_normal_(l.weight.data, std=std)
        l.bias.data.fill_(0.0)





class DynamicsModel(LightningModule):

    def __init__(self, obs_dim, act_dim, rew_dim, configs, device,
                    obs_bias=None, obs_scale=None,
                    act_bias=None, act_scale=None,
                    out_bias=None, out_scale=None) -> None:
        # print('init SimpleModel!')
        super(DynamicsModel, self).__init__() # To automatically use 'def forward'
        # if seed:
        #     random.seed(seed), np.random.seed(seed), T.manual_seed(seed)
        self.val = False

        self.configs = configs
        self._device_ = device

        self.obs_dim = obs_dim
        self.act_dim = act_dim
        self.inp_dim = inp_dim = obs_dim + act_dim
        self.out_dim = out_dim = obs_dim + rew_dim
        self.normalization(obs_bias, obs_scale, act_bias, act_scale, out_bias, out_scale)

        net_configs = configs['world_model']['network']
        net_arch = net_configs['arch']

        self.mu_log_sigma_net = MLPNet(inp_dim, 0, net_configs)
        self.mu = nn.Linear(net_arch[-1], out_dim)
        if configs['world_model']['type'][0] == 'P':
            self.log_sigma = nn.Linear(net_arch[-1], out_dim)

        self.min_log_sigma = nn.Parameter( -10.0 * T.ones([1, out_dim]),
                                          requires_grad=configs['world_model']['learn_log_sigma_limits'])
        self.max_log_sigma = nn.Parameter(T.ones([1, out_dim]) / 2.0,
                                          requires_grad=configs['world_model']['learn_log_sigma_limits'])
        self.reparam_noise = 1e-6

        self.apply(init_weights_)

        self.normalize = True
        self.normalize_out = True

        self.gnll_loss = nn.GaussianNLLLoss()
        self.mse_loss = nn.MSELoss()

        # self.to(self._device_)



    def get_model_dist_params(self, ips):
        net_out = self.mu_log_sigma_net(ips)
        mu, log_sigma = self.mu(net_out), self.log_sigma(net_out)
        log_sigma = self.max_log_sigma - F.softplus(self.max_log_sigma - log_sigma)
        log_sigma = self.min_log_sigma + F.softplus(log_sigma - self.min_log_sigma)

        sigma = T.exp(log_sigma)
        sigma_inv = T.tensor([0.0]) #T.exp(-log_sigma)

        # if T.mean(T.mean(sigma, dim=0)) > 1e2:
        #     # print(f'normed_o={normed_o}')
        #     # print(f'mu={mu}')
        #     print('log_sigma: ', log_sigma)
        #     # print('sigma: ', sigma)
        #     print(f'sigma_mean={T.mean(T.mean(sigma, dim=0))}')
        #     exit()

        return mu, log_sigma, sigma, sigma_inv


    # def deterministic(self, mu):
    #     pass


    def normalization(self, obs_bias=None, obs_scale=None,
                            act_bias=None, act_scale=None,
                            out_bias=None, out_scale=None):

        device = self._device_

        if obs_bias is None:
            self.obs_bias   = T.zeros(self.obs_dim)
            self.obs_scale  = T.ones(self.obs_dim)
            self.act_bias   = T.zeros(self.act_dim)
            self.act_scale  = T.ones(self.act_dim)
            self.out_bias   = T.zeros(self.out_dim)
            self.out_scale  = T.ones(self.out_dim)

        self.obs_bias   = self.obs_bias.to(device)
        self.obs_scale  = self.obs_scale.to(device)
        self.act_bias   = self.act_bias.to(device)
        self.act_scale  = self.act_scale.to(device)
        self.out_bias   = self.out_bias.to(device)
        self.out_scale  = self.out_scale.to(device)
        self.mask = self.out_scale >= epsilon


    def forward(self, o, a, deterministic= False):
        print('self.obs_bias: ', self.obs_bias)
        normed_o = (o - self.obs_bias)/(self.obs_scale + epsilon)
        normed_a = (a - self.act_bias)/(self.act_scale + epsilon)

        ips = T.as_tensor(T.cat([normed_o, normed_a], dim=-1), dtype=T.float32).to(self._device_)

        mu, log_sigma, sigma, sigma_inv = self.get_model_dist_params(
            T.as_tensor(ips, dtype=T.float32).to(self._device_))

        if self.normalize_out:
            mu = mu * (self.out_scale + epsilon) + self.out_bias

        return mu, log_sigma, sigma, sigma_inv


    def train_Model(self, data_module, m):
        device = self._device_
        # device = 'gpu' if self._device_=='cuda' else self._device_

        self.m = m

        M = self.configs['world_model']['num_ensembles']
        model_type = self.configs['world_model']['type']
        num_elites = self.configs['world_model']['num_elites']
        wm_epochs = self.configs['algorithm']['learning']['grad_WM_steps']

        batch_size = self.configs['world_model']['network']['batch_size']
        dropout = self.configs['world_model']['network']['dropout']
        # env_buffer.device = 'cpu'

        # data = DataModule(env_buffer, batch_size)
        # if dropout != None: self.train()

        early_stop_callback = EarlyStopping(monitor="J_val",
                                            min_delta=0.0,
                                            patience=5,
                                            # verbose=False,
                                            mode="max"
                                            )

        self.trainer = Trainer(
                          # max_epochs=wm_epochs,
                          # log_every_n_steps=2,
                          # accelerator=device, devices='auto',
                          gpus=1,
                          enable_model_summary=False,
                          enable_checkpointing=False,
                          progress_bar_refresh_rate=20,
                          # log_save_interval=100,
                          logger=False, #self.pl_logger,
                          callbacks=[early_stop_callback],
                          )

        self.normalize_out = False
        self.trainer.fit(self, data_module)
        self.normalize_out = True

        # print('\nNormalized:')
        # print(f'obs_bias={self.obs_bias}, \nobs_scale={self.obs_scale}')
        # print(f'act_bias={self.act_bias}, \nact_scale={self.act_scale}')
        # print(f'out_bias={self.out_bias}, \nout_scale={self.out_scale}')

        # if dropout != None: self.eval()

        if self.val:
            return self.train_log, self.val_log
        else:
            return self.train_log, None


    def test_Model(self, data_module):
        self.trainer.test(self, data_module)
        return self.test_loss, self.wm_mu, self.wm_sigma


	### PyTorch Lightning ###
	# add: dropouts, regulaizers
    def configure_optimizers(self):
        opt = 'T.optim.' + self.configs['world_model']['network']['optimizer']
        lr = self.configs['world_model']['network']['lr']
        optimizer = eval(opt)(self.parameters(), lr=lr)
        return optimizer


    def training_step(self, batch, batch_idx):
        self.train_log = dict()

        Jmu, Jsigma, J = self.compute_objective(batch)

        # self.log(f'Model {self.m+1}, Jmean_train', Jmean.item(), prog_bar=True)
        self.log(f'Model {self.m+1}, J_train', J.item(), prog_bar=True)

        self.train_log['mu'] = Jmu.item()
        # self.train_log['sigma'] = Jsigma.item()
        self.train_log['total'] = J.item()

        return J


    def validation_step(self, batch, batch_idx):
        self.val = True
        self.val_log = dict()

        Jmean, Jsigma, J = self.compute_objective(batch)

        # self.log("Jmean_val", Jmean.item(), prog_bar=True)
        self.log("J_val", J.item(), prog_bar=True)

        self.val_log['mu'] = Jmean.item()
        # self.val_log['sigma'] = Jsigma.item()
        self.val_log['total'] = J.item()


    def test_step(self, batch, batch_idx):
        # Model prediction performance
        loss, wm_mu, wm_sigma = self.compute_test_loss(batch)
        self.log("mse_loss", loss.item(), prog_bar=True)
        self.test_loss = loss.item()
        self.wm_mu = wm_mu
        self.wm_sigma = wm_sigma


    def get_progress_bar_dict(self):
        # don't show the version number
        items = super().get_progress_bar_dict()
        items.pop("loss", None)
        return items


    def compute_objective(self, batch):
        O, A, R, O_next, D = batch
        D = T.as_tensor(D, dtype=T.bool).to(self._device_)

        if self.normalize:
            # print('compute_objective: normalize')
            obs_bias, act_bias = T.mean(O, dim=0), T.mean(A, dim=0)
            obs_scale, act_scale = T.mean(T.abs(O - obs_bias), dim=0), T.mean(T.abs(A - act_bias), dim=0)
            out_bias = T.mean(O - O_next, dim=0)
            out_scale = T.mean(T.abs(O - O_next - out_bias), dim=0)
            self.normalization(obs_bias, obs_scale, act_bias, act_scale, out_bias, out_scale)

        mu, log_sigma, sigma, sigma_inv = self(O, A) # dyn_delta, reward
        mu_target = T.cat([O_next - O, R], dim=-1)

        # Gaussian NLL loss
        Jmu = T.tensor([0.0]) #T.mean(T.mean(T.square(mu - mu_target) * sigma_inv * ~D, dim=-1), dim=-1) # batch loss
        Jsigma = T.tensor([0.0]) #T.mean(T.mean(log_sigma * ~D, dim=-1), dim=-1)
        # Jgnll = Jmu + Jsigma
        Jgnll = self.gnll_loss(mu, mu_target, sigma)
        Jwl2 = self.weight_l2_loss()
        J = Jgnll + Jwl2
        J += 0.01 * ( T.sum(self.max_log_sigma) - T.sum(self.min_log_sigma) ) # optimize bounds

        return Jmu, Jsigma, J


    # def compute_l2_loss(self, l2_loss_coefs: Union[float, List[float]]):
    def weight_l2_loss(self): # must have 4 hid-layers in the WorldModel
        l2_loss_coefs = [0.000025, 0.00005, 0.000075, 0.000075, 0.0001, 0.0001]
        weight_norms = []
        for name, weight in self.named_parameters():
        	if "weight" in name:
        		weight_norms.append(weight.norm(2))
        weight_norms = T.stack(weight_norms, dim=0)
        # print('l2_loss_coefs: ', T.tensor(l2_loss_coefs, device=weight_norms.device))
        # print('weight_norms: ', weight_norms)
        weight_decay = (T.tensor(l2_loss_coefs, device=weight_norms.device) * weight_norms).sum()
        return weight_decay


    def compute_test_loss(self, batch):
        O, A, R, O_next, D = batch
        D = T.as_tensor(D, dtype=T.bool).to(self._device_)

        mu, log_sigma, sigma, sigma_inv = self(O, A) # dyn_delta, reward
        mu_target = T.cat([O_next - O, R], dim=-1)

        loss = self.mse_loss(mu, mu_target)

        wm_mu = T.mean(T.mean(mu, dim=0))
        wm_sigma = T.mean(T.mean(sigma, dim=0))

        return loss, wm_mu, wm_sigma
