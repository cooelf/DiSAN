from configs import cfg
from src.utils.record_log import _logger
import tensorflow as tf

from src.model.model_template import ModelTemplate
from src.nn_utils.nn import linear
from src.nn_utils.integration_func import multi_dimensional_attention, generate_embedding_mat,\
    directional_attention_with_dense


class ModelExpEmbDirMulAttn(ModelTemplate):
    def __init__(self, token_emb_mat, glove_emb_mat, tds, cds, tl, scope):
        super(ModelExpEmbDirMulAttn, self).__init__(token_emb_mat, glove_emb_mat, tds, cds, tl, scope)
        self.update_tensor_add_ema_and_opt()

    def build_network(self):
        _logger.add()
        _logger.add('building %s neural network structure...' % cfg.network_type)
        tds, cds = self.tds, self.cds
        tl = self.tl
        tel, cel, cos, ocd, fh = self.tel, self.cel, self.cos, self.ocd, self.fh
        hn = self.hn
        bs, sl1, sl2 = self.bs, self.sl1, self.sl2

        with tf.variable_scope('emb'):
            token_emb_mat = generate_embedding_mat(tds, tel, init_mat=self.token_emb_mat,
                                                   extra_mat=self.glove_emb_mat, extra_trainable=self.finetune_emb,
                                                   scope='gene_token_emb_mat')
            s1_emb = tf.nn.embedding_lookup(token_emb_mat, self.sent1_token)  # bs,sl1,tel
            s2_emb = tf.nn.embedding_lookup(token_emb_mat, self.sent2_token)  # bs,sl2,tel
            self.tensor_dict['s1_emb'] = s1_emb
            self.tensor_dict['s2_emb'] = s2_emb

        with tf.variable_scope('ct_attn'):
            s1_fw = directional_attention_with_dense(
                s1_emb, self.sent1_token_mask, 'forward', 'dir_attn_fw',
                cfg.dropout, self.is_train, cfg.wd,
                tensor_dict=self.tensor_dict, name='s1_fw_attn')
            s1_bw = directional_attention_with_dense(
                s1_emb, self.sent1_token_mask, 'backward', 'dir_attn_bw',
                cfg.dropout, self.is_train, cfg.wd,
                tensor_dict=self.tensor_dict, name='s1_bw_attn')

            s1_seq_rep = tf.concat([s1_fw, s1_bw], -1)

            tf.get_variable_scope().reuse_variables()

            s2_fw = directional_attention_with_dense(
                s2_emb, self.sent2_token_mask, 'forward', 'dir_attn_fw',
                cfg.dropout, self.is_train, cfg.wd,
                tensor_dict=self.tensor_dict, name='s2_fw_attn')
            s2_bw = directional_attention_with_dense(
                s2_emb, self.sent2_token_mask, 'backward', 'dir_attn_bw',
                cfg.dropout, self.is_train, cfg.wd,
                tensor_dict=self.tensor_dict, name='s2_bw_attn')
            s2_seq_rep = tf.concat([s2_fw, s2_bw], -1)

        with tf.variable_scope('sent_enc_attn'):
            s1_rep = multi_dimensional_attention(
                s1_seq_rep, self.sent1_token_mask, 'multi_dimensional_attention',
                cfg.dropout, self.is_train, cfg.wd,
                tensor_dict=self.tensor_dict, name='s1_attn')
            tf.get_variable_scope().reuse_variables()
            s2_rep = multi_dimensional_attention(
                s2_seq_rep, self.sent2_token_mask, 'multi_dimensional_attention',
                cfg.dropout, self.is_train, cfg.wd,
                tensor_dict=self.tensor_dict, name='s2_attn')

            self.tensor_dict['s1_rep'] = s1_rep
            self.tensor_dict['s2_rep'] = s2_rep

        with tf.variable_scope('output'):
            out_rep = tf.concat([s1_rep, s2_rep, s1_rep - s2_rep, s1_rep * s2_rep], -1)
            pre_output = tf.nn.elu(linear([out_rep], hn, True, 0., scope= 'pre_output', squeeze=False,
                                           wd=cfg.wd, input_keep_prob=cfg.dropout,is_train=self.is_train))
            logits = linear([pre_output], self.output_class, True, 0., scope= 'logits', squeeze=False,
                            wd=cfg.wd, input_keep_prob=cfg.dropout,is_train=self.is_train)
            self.tensor_dict[logits] = logits
        return logits # logits



