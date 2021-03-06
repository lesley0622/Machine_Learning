import sys
sys.path.append("../")

from utils import *
from ImageNet.GoogleNet import inception_v1


class Ocr4LenCnnModel(object):
    def __init__(self, is_training, ):
        self.is_training = is_training
        self.__build_model()

    def __build_model(self):
        num_classes = len(src_data)
        self.x = tf.placeholder(tf.float32, shape=[None, PIC_HEIGHT, PIC_WIDTH, PIC_CHANNELS], name='x')
        self.y = tf.placeholder(tf.int64, shape=[None, 4], name='y')
        self.keep_prob = tf.placeholder("float", name='keep_prob')
        self.global_step = tf.Variable(0, trainable=False)
        self.training = tf.placeholder(tf.bool, name='training')

        net = inception_v1(self.x, 4*num_classes)
        logits = tf.reshape(net, [-1, 4, num_classes])

        tf.losses.sparse_softmax_cross_entropy(labels=self.y, logits=logits)
        self.loss = tf.losses.get_total_loss(add_regularization_losses=True, name='total_loss')

        self.y_pred = tf.argmax(logits, 2)
        self.correct_prediction = tf.equal(self.y_pred, self.y)

    def check_accuracy(self, iterator, sess, op_type):
        sess.run(iterator.initializer,
                 feed_dict={iterator.filenames: [FLAGS.train_records_dir if op_type == "train" else FLAGS.test_records_dir]})
        num_correct, num_samples = 0, 0
        while True:
            try:
                image, label = sess.run([iterator.image, iterator.label])
                if image is None: break
                correct_pred = sess.run(self.correct_prediction,
                                        feed_dict={self.x: image,
                                                   self.y: label,
                                                   self.keep_prob: 1.0,
                                                   self.training: False})
                num_correct += correct_pred.sum()
                num_samples += correct_pred.shape[0] * 4
            except tf.errors.OutOfRangeError:
                break

        # Return the fraction of datapoints that were correctly classified
        acc = float(num_correct) / num_samples
        return acc

    def train_model(self):
        if not self.is_training:
            raise ValueError("this is compute mode, please reconstruct model with is_training")

        dataset = DataIterator()
        iterator = dataset.get_iterator(batch_size=FLAGS.batch_size)

        lr = tf.train.exponential_decay(
            learning_rate=FLAGS.learning_rate,
            global_step=self.global_step,
            decay_steps=FLAGS.decay_steps,
            decay_rate=FLAGS.decay_rate,
            staircase=False,
            name='learning_rate'
        )

        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        with tf.control_dependencies(update_ops):
            train_step = tf.train.AdamOptimizer(lr).minimize(self.loss)

        config = tf.ConfigProto()
        config.gpu_options.per_process_gpu_memory_fraction = 0.5
        config.gpu_options.allow_growth = True

        with tf.Session(config=config) as sess:
            sess.run(tf.global_variables_initializer())

            saver = tf.train.Saver()
            ckpt = tf.train.get_checkpoint_state(FLAGS.model_path)
            if ckpt is not None:
                path = ckpt.model_checkpoint_path
                saver.restore(sess, path)

            current_epoch = sess.run(self.global_step)
            current_epoch += 1

            while True:
                if current_epoch > FLAGS.epochs: break
                sess.run(iterator.initializer,
                         feed_dict={iterator.filenames: [FLAGS.train_records_dir]})
                while True:
                    try:
                        image, label = sess.run([iterator.image, iterator.label])
                        if image is None: break
                        _ = sess.run(train_step, feed_dict={self.x: image,
                                                            self.y: label,
                                                            self.keep_prob: FLAGS.keep_prob,
                                                            self.training: True})
                    except tf.errors.OutOfRangeError:
                        break

                if current_epoch % 10 == 0:
                    train_acc = self.check_accuracy(iterator, sess, "train")
                    val_acc = self.check_accuracy(iterator, sess, "test")
                    logging.info('epoch: {}, Train accuracy: {}, Val accuracy: {}'.format(current_epoch, train_acc, val_acc))
                    sess.run(tf.assign(self.global_step, current_epoch))
                    saver.save(sess, FLAGS.model_path + 'points', global_step=current_epoch)

                current_epoch += 1

