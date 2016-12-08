# -*- coding:utf-8 -*-

'''
Sequence generation implemented in Tensorflow
2016-12-3
'''
import tensorflow as tf
from tensorflow.python.ops import rnn_cell
from tensorflow.python.ops import seq2seq

import numpy as np

class Model():
    def __init__(self, args, infer=False):
        self.args = args
	# infer is test mode or evaluation mode
        if infer:
            args.batch_size = 1
            args.seq_length = 1

        if args.model == 'rnn':
            cell_fn = rnn_cell.BasicRNNCell
        elif args.model == 'gru':
            cell_fn = rnn_cell.GRUCell
        elif args.model == 'lstm':
            cell_fn = rnn_cell.BasicLSTMCell
        else:
            raise Exception("model type not supported: {}".format(args.model))

	# build multi-layer rnn cell
        cell = cell_fn(args.rnn_size)
        self.cell = cell = rnn_cell.MultiRNNCell([cell] * args.num_layers)

	# input_data is an integer tensor, only need to set its index of word dictionary
        self.input_data = tf.placeholder(tf.int32, [args.batch_size, args.seq_length])
	# targets is an integer tensor, only need to set its index of word dictionary
        self.targets = tf.placeholder(tf.int32, [args.batch_size, args.seq_length])
	# zero-filled state RNN tensor
        self.initial_state = cell.zero_state(args.batch_size, tf.float32)

	# language model scope
        with tf.variable_scope('rnnlm'):
	    # softmax layer,from rnn size to vocabulary size
            softmax_w = tf.get_variable("softmax_w", [args.rnn_size, args.vocab_size])
            softmax_b = tf.get_variable("softmax_b", [args.vocab_size])
            with tf.device("/cpu:0"):
		# word embedding
                embedding = tf.get_variable("embedding", [args.vocab_size, args.rnn_size])
		# split along dimension 1 to args.seq_length parts
                inputs = tf.split(1, args.seq_length, tf.nn.embedding_lookup(embedding, self.input_data))
		# word embedded inputs
		# remove dimension of size 1
                inputs = [tf.squeeze(input_, [1]) for input_ in inputs]

        def loop(prev, _):
	    # attain the softmax sum
            prev = tf.matmul(prev, softmax_w) + softmax_b
	    # prev shouldn't be covered in bp updating
            prev_symbol = tf.stop_gradient(tf.argmax(prev, 1))
	    # output the prev_symbol's word embedding
            return tf.nn.embedding_lookup(embedding, prev_symbol)

        outputs, last_state = seq2seq.rnn_decoder(inputs, self.initial_state, cell, loop_function=loop if infer else None, scope='rnnlm')
        output = tf.reshape(tf.concat(1, outputs), [-1, args.rnn_size])
        self.logits = tf.matmul(output, softmax_w) + softmax_b
	# probability distribution of output
        self.probs = tf.nn.softmax(self.logits)
        loss = seq2seq.sequence_loss_by_example([self.logits],
                [tf.reshape(self.targets, [-1])],
                [tf.ones([args.batch_size * args.seq_length])],
                args.vocab_size)
        self.cost = tf.reduce_sum(loss) / args.batch_size / args.seq_length
        self.final_state = last_state
        self.lr = tf.Variable(0.0, trainable=False)
        tvars = tf.trainable_variables()
        grads, _ = tf.clip_by_global_norm(tf.gradients(self.cost, tvars),
                args.grad_clip)
        optimizer = tf.train.AdamOptimizer(self.lr)
        self.train_op = optimizer.apply_gradients(zip(grads, tvars))

    # generation process
    def sample(self, sess, words, vocab, num=200, prime=u'我们', sampling_type=1):
	'''
	self.cell.zero_state = tf.convert_to_tensor(self.cell.zero_state)
        state = self.cell.zero_state(1,tf.float32).eval()
	'''
	state = sess.run(self.cell.zero_state(1, tf.float32))

	#prime = prime.decode('utf-8')
        for word in prime:
            x = np.zeros((1, 1))
            x[0, 0] = vocab[word]
            feed = {self.input_data: x, self.initial_state:state}
            [state] = sess.run([self.final_state], feed)

        def weighted_pick(weights):
            t = np.cumsum(weights)
            s = np.sum(weights)
            return(int(np.searchsorted(t, np.random.rand(1)*s)))

        ret = prime
        word = prime[-1]
        for n in range(num):
            x = np.zeros((1, 1))
            x[0, 0] = vocab[word]
            feed = {self.input_data: x, self.initial_state:state}
            [probs, state] = sess.run([self.probs, self.final_state], feed)
            p = probs[0]

            if sampling_type == 0:
                sample = np.argmax(p)
            elif sampling_type == 2:
                if word == '\n':
                    sample = weighted_pick(p)
                else:
                    sample = np.argmax(p)
            else: # sampling_type == 1 default:
                sample = weighted_pick(p)

            pred = words[sample]
            ret += pred
            word = pred
        return ret
