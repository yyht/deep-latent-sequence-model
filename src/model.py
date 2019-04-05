import torch
import torch.nn.init as init
from torch.autograd import Variable
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
import torch.nn.functional as F

import gc
import numpy as np
from utils import *
from noise import NoiseLayer

class MlpAttn(nn.Module):
  def __init__(self, hparams):
    super(MlpAttn, self).__init__()
    self.hparams = hparams
    self.dropout = nn.Dropout(hparams.dropout)
    self.w_trg = nn.Linear(self.hparams.d_model, self.hparams.d_model)
    self.w_att = nn.Linear(self.hparams.d_model, 1)
    # if self.hparams.cuda:
    #   self.w_trg = self.w_trg.cuda()
    #   self.w_att = self.w_att.cuda()

  def forward(self, q, k, v, attn_mask=None):
    batch_size, d_q = q.size()
    batch_size, len_k, d_k = k.size()
    batch_size, len_v, d_v = v.size()
    # v is bi-directional encoding of source
    assert d_k == d_q
    #assert 2*d_k == d_v
    assert len_k == len_v
    # (batch_size, len_k, d_k)
    att_src_hidden = torch.tanh(k + self.w_trg(q).unsqueeze(1))
    # (batch_size, len_k)
    att_src_weights = self.w_att(att_src_hidden).squeeze(2)
    if not attn_mask is None:
      att_src_weights.data.masked_fill_(attn_mask, -self.hparams.inf)
    att_src_weights = F.softmax(att_src_weights, dim=-1)
    att_src_weights = self.dropout(att_src_weights)
    ctx = torch.bmm(att_src_weights.unsqueeze(1), v).squeeze(1)
    return ctx

class Encoder(nn.Module):
  def __init__(self, hparams, *args, **kwargs):
    super(Encoder, self).__init__()

    self.hparams = hparams
    self.word_emb = nn.Embedding(self.hparams.src_vocab_size,
                                 self.hparams.d_word_vec,
                                 padding_idx=hparams.pad_id)

    self.layer = nn.LSTM(self.hparams.d_word_vec,
                         self.hparams.d_model,
                         bidirectional=True,
                         dropout=hparams.dropout)

    # bridge from encoder state to decoder init state
    self.bridge = nn.Linear(hparams.d_model * 2, hparams.d_model, bias=False)

    self.dropout = nn.Dropout(self.hparams.dropout)

  def forward(self, x_train, x_len):
    """Performs a forward pass.
    Args:
      x_train: Torch Tensor of size [batch_size, max_len]
      x_mask: Torch Tensor of size [batch_size, max_len]. 1 means to ignore a
        position.
      x_len: [batch_size,]
    Returns:
      enc_output: Tensor of size [batch_size, max_len, d_model].
    """
    batch_size, max_len = x_train.size()
    x_train = x_train.transpose(0, 1)
    # [batch_size, max_len, d_word_vec]
    word_emb = self.word_emb(x_train)
    word_emb = self.dropout(word_emb)
    packed_word_emb = pack_padded_sequence(word_emb, x_len)
    enc_output, (ht, ct) = self.layer(packed_word_emb)
    enc_output, _ = pad_packed_sequence(enc_output,  padding_value=self.hparams.pad_id)
    #enc_output, (ht, ct) = self.layer(word_emb)
    enc_output = enc_output.permute(1, 0, 2)

    dec_init_cell = self.bridge(torch.cat([ct[0], ct[1]], 1))
    dec_init_state = F.tanh(dec_init_cell)
    dec_init = (dec_init_state, dec_init_cell)

    return enc_output, dec_init

class Decoder(nn.Module):
  def __init__(self, hparams, word_emb):
    super(Decoder, self).__init__()
    self.hparams = hparams

    #self.attention = DotProdAttn(hparams)
    self.attention = MlpAttn(hparams)
    # transform [ctx, h_t] to readout state vectors before softmax
    self.ctx_to_readout = nn.Linear(hparams.d_model * 2 + hparams.d_model, hparams.d_model, bias=False)
    self.readout = nn.Linear(hparams.d_model, hparams.src_vocab_size, bias=False)
    self.word_emb = word_emb
    self.attr_emb = nn.Embedding(self.hparams.trg_vocab_size,
                                 self.hparams.d_word_vec,
                                 padding_idx=hparams.trg_pad_id)

    # input: [y_t-1, input_feed]
    self.layer = nn.LSTMCell(2 * self.hparams.d_word_vec + hparams.d_model * 2,
                             hparams.d_model)
    self.dropout = nn.Dropout(hparams.dropout)

  # TODO(junxian): why only use y embedding in the first time stamp ?
  def forward(self, x_enc, x_enc_k, dec_init, x_mask, y_train, y_mask, y_len, x_train, x_len):
    # get decoder init state and cell, use x_ct
    """
    x_enc: [batch_size, max_x_len, d_model * 2]
    """
    batch_size_x = x_enc.size()[0]
    batch_size, x_max_len = x_train.size()
    assert batch_size_x == batch_size
    hidden = dec_init
    input_feed = torch.zeros((batch_size, self.hparams.d_model * 2),
        requires_grad=False, device=self.hparams.device)
    # if self.hparams.cuda:
    #   input_feed = input_feed.cuda()
    # [batch_size, y_len, d_word_vec]
    x_emb = self.word_emb(x_train)

    pre_readouts = []
    logits = []
    # init with attr emb
    attr_emb =self.attr_emb(y_train)
    attr_emb = attr_emb.sum(dim=1) / y_len.unsqueeze(1)
    for t in range(x_max_len):
      x_emb_tm1 = x_emb[:, t, :]
      x_input = torch.cat([x_emb_tm1, attr_emb, input_feed], dim=1)

      h_t, c_t = self.layer(x_input, hidden)
      ctx = self.attention(h_t, x_enc_k, x_enc, attn_mask=x_mask)
      pre_readout = F.tanh(self.ctx_to_readout(torch.cat([h_t, ctx], dim=1)))
      pre_readout = self.dropout(pre_readout)
      pre_readouts.append(pre_readout)

      input_feed = ctx
      hidden = (h_t, c_t)
      
    # [len_y, batch_size, trg_vocab_size]
    logits = self.readout(torch.stack(pre_readouts)).transpose(0, 1).contiguous()
    return logits

  def step(self, x_enc, x_enc_k, x_mask, y_tm1, dec_state, ctx_t, data):
    #y_emb_tm1 = self.word_emb(y_tm1)
    y_emb_tm1 = y_tm1
    y_input = torch.cat([y_emb_tm1, ctx_t], dim=1)
    h_t, c_t = self.layer(y_input, dec_state)
    ctx = self.attention(h_t, x_enc_k, x_enc, attn_mask=x_mask)
    pre_readout = F.tanh(self.ctx_to_readout(torch.cat([h_t, ctx], dim=1)))
    logits = self.readout(pre_readout)

    return logits, (h_t, c_t), ctx

class Seq2Seq(nn.Module):

  def __init__(self, hparams, data):
    super(Seq2Seq, self).__init__()
    self.encoder = Encoder(hparams)
    self.decoder = Decoder(hparams, self.encoder.word_emb)
    self.data = data
    # transform encoder state vectors into attention key vector
    self.enc_to_k = nn.Linear(hparams.d_model * 2, hparams.d_model, bias=False)
    self.hparams = hparams
    self.noise = NoiseLayer(hparams.word_blank, hparams.word_dropout,
        hparams.word_shuffle, hparams.pad_id, hparams.unk_id)

    # if self.hparams.cuda:
    #   self.enc_to_k = self.enc_to_k.cuda()

  def forward(self, x_train, x_mask, x_len, x_pos_emb_idxs, y_train, y_mask, y_len, y_pos_emb_idxs, y_sampled, y_sampled_mask, y_sampled_len):
    y_len = torch.tensor(y_len, dtype=torch.float, device=self.hparams.device, requires_grad=False)
    y_sampled_len = torch.tensor(y_sampled_len, dtype=torch.float, device=self.hparams.device, 
        requires_grad=False)

    # first translate based on y_sampled
    # get_translation is to get translation one by one so there is no length order concern
    # index is a list which represents original position in this batch after reordering 
    # translated sentences
    # on-the-fly back translation
    with torch.no_grad():
      x_trans, x_trans_mask, x_trans_len, index = self.get_translations(x_train, x_mask, x_len, y_sampled, y_sampled_mask, y_sampled_len)

    index = torch.tensor(index.copy(), dtype=torch.long, requires_grad=False, device=self.hparams.device)

    x_trans_enc, x_trans_init = self.encoder(x_trans, x_trans_len)
    x_trans_enc = torch.index_select(x_trans_enc, 0, index)
    new_x_trans_init = []
    new_x_trans_init.append(torch.index_select(x_trans_init[0], 0, index))
    new_x_trans_init.append(torch.index_select(x_trans_init[1], 0, index))
    x_trans_init = (new_x_trans_init[0], new_x_trans_init[1])

    x_trans_enc_k = self.enc_to_k(x_trans_enc)
    trans_logits = self.decoder(x_trans_enc, x_trans_enc_k, x_trans_init, x_trans_mask, y_train, y_mask, y_len, x_train, x_len)

    # then denoise encode
    # [batch_size, x_len, d_model * 2]
    x_noise, x_noise_mask, x_noise_len, index  = self.add_noise(x_train, x_mask, x_len)
    x_noise_enc, x_noise_init = self.encoder(x_noise, x_noise_len)
    x_noise_enc = torch.index_select(x_noise_enc, 0, index)
    new_x_noise_init = []
    new_x_noise_init.append(torch.index_select(x_noise_init[0], 0, index))
    new_x_noise_init.append(torch.index_select(x_noise_init[1], 0, index))
    x_noise_init = (new_x_noise_init[0], new_x_noise_init[1])

    x_noise_enc_k = self.enc_to_k(x_noise_enc)
    # [batch_size, y_len-1, trg_vocab_size]
    noise_logits = self.decoder(x_noise_enc, x_noise_enc_k, x_noise_init, x_noise_mask, y_train, y_mask, y_len, x_train, x_len)
    return trans_logits, noise_logits

  def get_translations(self, x_train, x_mask, x_len, y_sampled, y_sampled_mask, y_sampled_len):
    # list
    translated_x = self.translate(x_train, x_mask, y_sampled, y_sampled_mask, y_sampled_len, beam_size=1)
    translated_x = [[self.hparams.bos_id]+x+[self.hparams.eos_id] for x in translated_x]


    translated_x = np.array(translated_x)
    trans_len = [len(i) for i in translated_x]
    index = np.argsort(trans_len)
    index = index[::-1]
    translated_x = translated_x[index].tolist()
    x_trans, x_mask, x_count, x_len, _ = self.data._pad(translated_x, self.hparams.pad_id)
    return x_trans, x_mask, x_len, index

  def add_noise(self, x_train, x_mask, x_len):
    """
    Args:
      x_train: (batch, seq_len, dim)
      x_mask: (batch, seq_len)
      x_len: a list of lengths

    Returns: x_train, mask, x_len, index
      index: a numpy array to show the original position before reordering
    """
    x_train = x_train.transpose(0, 1)
    x_train, x_len = self.noise(x_train, x_len)
    x_train = x_train.transpose(0, 1)

    index = np.argsort(x_len)
    index = index[::-1]
    index = torch.tensor(index.copy(), dtype=torch.long, requires_grad=False, device=self.hparams.device)

    x_train = torch.index_select(x_train, 0, index)
    x_len = [x_len[i] for i in index]

    bs, max_len = x_train.size()
    mask = [[0] * x_len[i] + [1] * (max_len - x_len[i]) for i in range(bs)]
    mask = torch.tensor(mask, dtype=torch.uint8, requires_grad=False, device=self.hparams.device)
    return x_train, mask, x_len, index

  def translate(self, x_train, x_mask, y, y_mask, y_len, max_len=100, beam_size=2, poly_norm_m=0):
    hyps = []
    batch_size = x_train.size(0)
    for i in range(batch_size):
      x = x_train[i,:].unsqueeze(0)
      mask = x_mask[i,:].unsqueeze(0)
      y_i = y[i,:].unsqueeze(0)
      y_i_mask = y_mask[i,:].unsqueeze(0)
      y_i_len = y_len[i].unsqueeze(0)
      hyp = self.translate_sent(x, mask, y_i, y_i_mask, y_i_len, max_len=max_len, beam_size=beam_size, poly_norm_m=poly_norm_m)[0]
      hyps.append(hyp.y[1:-1])
    return hyps

  def translate_sent(self, x_train, x_mask, y, y_mask, y_len, max_len=100, beam_size=5, poly_norm_m=0):
    x_len = [x_train.size(1)]
    x_enc, dec_init = self.encoder(x_train, x_len)
    x_enc_k = self.enc_to_k(x_enc)
    length = 0
    completed_hyp = []
    input_feed = torch.zeros((1, self.hparams.d_model * 2),
      requires_grad=False, device=self.hparams.device)
    # if self.hparams.cuda:
    #   input_feed = input_feed.cuda()
    active_hyp = [Hyp(state=dec_init, y=[self.hparams.bos_id], ctx_tm1=input_feed, score=0.)]
    attr_emb = self.decoder.attr_emb(y).sum(1) / y_len
    while len(completed_hyp) < beam_size and length < max_len:
      length += 1
      new_hyp_score_list = []
      for i, hyp in enumerate(active_hyp):
        y_tm1 = torch.tensor([int(hyp.y[-1])], dtype=torch.long, 
          requires_grad=False, device=self.hparams.device)
        y_tm1 = self.decoder.word_emb(y_tm1)
        y_tm1 = torch.cat([y_tm1, attr_emb], dim=-1)
        # if length == 1:
        #   # ave attr emb
        #   y_tm1 = self.decoder.attr_emb(y).sum(1) / y_len.float()
        # else:
        #   y_tm1 = torch.LongTensor([int(hyp.y[-1])], device=self.hparams.device)
        #   y_tm1 = self.decoder.word_emb(y_tm1)
        logits, dec_state, ctx = self.decoder.step(x_enc, x_enc_k, x_mask, y_tm1, hyp.state, hyp.ctx_tm1, self.data)
        hyp.state = dec_state
        hyp.ctx_tm1 = ctx

        p_t = F.log_softmax(logits, -1).data
        if poly_norm_m > 0 and length > 1:
          new_hyp_scores = (hyp.score * pow(length-1, poly_norm_m) + p_t) / pow(length, poly_norm_m)
        else:
          new_hyp_scores = hyp.score + p_t
        new_hyp_score_list.append(new_hyp_scores)
      live_hyp_num = beam_size - len(completed_hyp)
      new_hyp_scores = np.concatenate(new_hyp_score_list).flatten()
      new_hyp_pos = (-new_hyp_scores).argsort()[:live_hyp_num]
      prev_hyp_ids = new_hyp_pos / self.hparams.src_vocab_size
      word_ids = new_hyp_pos % self.hparams.src_vocab_size
      new_hyp_scores = new_hyp_scores[new_hyp_pos]

      new_hypotheses = []
      for prev_hyp_id, word_id, hyp_score in zip(prev_hyp_ids, word_ids, new_hyp_scores):
        prev_hyp = active_hyp[int(prev_hyp_id)]
        hyp = Hyp(state=prev_hyp.state, y=prev_hyp.y+[word_id], ctx_tm1=prev_hyp.ctx_tm1, score=hyp_score)
        if word_id == self.hparams.eos_id:
          completed_hyp.append(hyp)
        else:
          new_hypotheses.append(hyp)
        #print(word_id, hyp_score)
      #exit(0)
      active_hyp = new_hypotheses

    if len(completed_hyp) == 0:
      completed_hyp.append(active_hyp[0])
    return sorted(completed_hyp, key=lambda x: x.score, reverse=True)

class Hyp(object):
  def __init__(self, state, y, ctx_tm1, score):
    self.state = state
    self.y = y
    self.ctx_tm1 = ctx_tm1
    self.score = score
