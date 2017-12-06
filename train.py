import argparse
import tensorflow as tf
from preprocess import *
from util import *
from models.CNNEmbed import CNNEmbed
from models.SentimentClassifier import SentimentClassifier
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"


def training_pass(sess, train_op, data_inds, target_inds, batch_target, placeholders, keep_prob):
    """
    Do a training pass through a batch of the data.

    Args:
        sess: Tensorflow session.
        train_op: Tensorflow training operation.
        data_inds (numpy.ndarray): The training data, as an array of indices.
        target_inds (numpy.ndarray): The next words to predict
        batch_target (numpy.ndarray): The target labels
        placeholders (list): Tensorflow placeholders used for training
        keep_prob (float): The keep prob, used for dropout

    Returns:
        None
    """

    indices_data_placeholder = placeholders[0]
    indices_target_placeholder = placeholders[1]
    target_place_holder = placeholders[2]
    kp_placeholder = placeholders[3]

    feed_dict = {indices_data_placeholder: data_inds, indices_target_placeholder: target_inds,
                 target_place_holder: batch_target, kp_placeholder: keep_prob}
    sess.run([train_op], feed_dict)


def main(args):

    context_len = args.context_len
    batch_size = args.batch_size
    num_filters = args.num_filters
    num_layers = args.num_layers
    pos_words_num = args.num_positive_words
    neg_words_num = args.num_negative_words
    num_residual = args.num_residual
    keep_prob = args.dropout_keep_prob
    embed_dim = args.embed_dim
    learning_rate = args.learning_rate
    data_dir = args.data_dir
    checkpoint_path = args.checkpoint_dir
    max_iter = args.max_iter
    k_max = 0

    if args.dataset == 'imdb':
        max_doc_len = 400
        split_class = 7
        unlabeled_class = 0
    else:
        # Using the amazon dataset
        max_doc_len = 200
        split_class = 3
        unlabeled_class = 2

    if args.model == 'CNN_pad':
        fixed_length = True
    else:
        # If using 'pool or topk'
        fixed_length = False
        if args.model == 'CNN_topk':
            k_max = args.top_k

    classifier_max_iter = 500

    vector_up_fn = os.path.join(args.cache_dir, 'vector_up.npy')
    train_data_inds_fn = os.path.join(args.cache_dir, 'train_data_indices.npy')
    train_labels_fn = os.path.join(args.cache_dir, 'train_labels.npy')
    test_data_indices_fn = os.path.join(args.cache_dir, 'test_data_indices.npy')
    test_labels_fn = os.path.join(args.cache_dir, 'test_labels.npy')

    ###########################################Preprocessing#########################################
    if not args.preprocessing:
        # Load the variables. This will generate an error if those files don't exist.
        vector_up = np.load(vector_up_fn)
        train_data_indices = np.load(train_data_inds_fn)
        train_labels = np.load(train_labels_fn)
        test_data_indices = np.load(test_data_indices_fn)
        test_labels = np.load(test_labels_fn)
    else:
        # Preprocess data
        if args.dataset == 'imdb':
            vector_up, train_data_indices, train_labels, test_data_indices, test_labels = get_data_imdb(data_dir, max_doc_len, fixed_length)
        else:
            vector_up, train_data_indices, train_labels, test_data_indices, test_labels = get_data_amazon(data_dir, max_doc_len, fixed_length)
        np.save(vector_up_fn, vector_up)
        np.save(train_data_inds_fn, train_data_indices)
        np.save(train_labels_fn, train_labels)
        np.save(test_data_indices_fn, test_data_indices)
        np.save(test_labels_fn, test_labels)

    #Get the index of zero vector
    zero_vector_index = vector_up.shape[0] - 1

    # Get the supervised train and test data
    # Build the model graphs
    print("all of our inputs follow NHWC: batch, height, width, channel.")
    train_data_indices_sup, test_data_indices_sup, \
    train_labels_sup, test_labels_sup = get_sup_data(train_data_indices, test_data_indices, train_labels, test_labels,
                 unlabeled_class, split_class, fixed_length, max_doc_len, args.num_classes, zero_vector_index)

    ###########################################Embedding learning Graph#########################################
    doc2vec_graph = tf.Graph()
    with doc2vec_graph.as_default(), tf.device("/gpu:0"):
        indices_data_placeholder = tf.placeholder(dtype=tf.int32, shape=[None, None])
        indices_target_placeholder = tf.placeholder(dtype=tf.int32, shape=[None, pos_words_num + neg_words_num])

        embedding = tf.get_variable("embedding", [vector_up.shape[0], embed_dim], dtype=tf.float32, trainable=True)
        assign_embedding_op = tf.assign(embedding, vector_up)
        inputs = tf.gather(embedding, indices_data_placeholder)
        inputs = tf.expand_dims(inputs, 3)
        inputs = tf.transpose(inputs, [0, 2, 1, 3])

        targets_embeds = tf.gather(embedding, indices_target_placeholder)
        targets_embeds = tf.expand_dims(targets_embeds, 3)
        targets_embeds = tf.transpose(targets_embeds, [0, 2, 1, 3])

        target_place_holder = tf.placeholder(tf.float32, [None, pos_words_num + neg_words_num])
        # Placeholder for dropout
        keep_prob_placeholder = tf.placeholder(dtype=tf.float32, name='dropout_rate')

        # build model
        _docCNN = CNNEmbed(inputs, targets_embeds, target_place_holder, keep_prob_placeholder, max_doc_len, embed_dim,
                           num_layers, num_filters, num_residual, k_max)

        global_step = tf.Variable(0, trainable=False)

        loss = _docCNN.loss()

        # input of the test (supervised learning) process
        test_obj_cal_output = tf.squeeze(_docCNN.res)

        # setting the learning rate
        # Not using learning rate decay
        learning_rate_t = tf.train.exponential_decay(learning_rate, global_step, sys.maxint, 0.99, staircase=True)
        optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate_t)
        grads_and_vars = optimizer.compute_gradients(loss)
        train_op = optimizer.apply_gradients(grads_and_vars)

        session_conf = tf.ConfigProto(allow_soft_placement=True, log_device_placement=False)
        sess_docCNN = tf.Session(config=session_conf)
        train_init_op_docCNN = tf.global_variables_initializer()
        saver = tf.train.Saver()

    ###########################################Classifier Graph######################################
    classifier_graph = tf.Graph()
    with classifier_graph.as_default(), tf.device('/gpu:0'):
        classifier_data_place_holder = tf.placeholder(tf.float32, [batch_size, embed_dim],
                                                      name="classifier_place_holder")
        classifier_label_place_holder = tf.placeholder(tf.float32, [batch_size])
        # Creating the classifier object.
        classifier = SentimentClassifier(classifier_data_place_holder, classifier_label_place_holder, embed_dim,
                                         batch_size, args.num_classes)
        classifier_loss_op = classifier.loss()

        classifier_predictions = tf.argmax(classifier.logits, 1, name="predictions")
        correct_predictions = tf.equal(classifier_predictions, tf.argmax(classifier.labels_one_hot, 1))
        train_accuracy_op = tf.reduce_mean(tf.cast(correct_predictions, "float"), name="train_accuracy")
        test_accuracy_op = tf.reduce_mean(tf.cast(correct_predictions, "float"), name="test_accuracy")

        classifier_optimizer = tf.train.MomentumOptimizer(0.0008, 0.9)
        classifier_grads_and_vars = classifier_optimizer.compute_gradients(classifier_loss_op)
        classifier_train_op = classifier_optimizer.apply_gradients(classifier_grads_and_vars)

        session_conf = tf.ConfigProto(allow_soft_placement=True, log_device_placement=False)
        train_init_op_classifier = tf.global_variables_initializer()
        sess_classifier = tf.Session(config=session_conf)

    ###########################################Training######################################
    # Initializing the variables.
    sess_docCNN.run(train_init_op_docCNN)
    sess_classifier.run(train_init_op_classifier)
    sess_docCNN.run(assign_embedding_op)
    overall_highest = 0

    batch_target = np.hstack((np.full((batch_size, pos_words_num), 1), np.full((batch_size, neg_words_num), 0)))

    # Batch generator
    batch_generator = BatchGenerator(train_data_indices, pos_words_num, neg_words_num, max_doc_len,
                                     context_len, vector_up.shape[0] - 1, batch_size)

    itr = 0
    # Training Loop
    while itr < max_iter:
        data_size = batch_generator.get_data_size()
        batch_per_epoch = data_size / batch_size
        print('Number of batches: {}'.format(batch_per_epoch))
        sess_docCNN.run(global_step.assign(itr))
        batch_generator.generate_training_batches()
        train_times = []
        placeholders = [indices_data_placeholder, indices_target_placeholder, target_place_holder,
                        keep_prob_placeholder]
        for i in range(batch_per_epoch):
            t1 = time.time()
            ret_val = batch_generator.get_data()
            data_inds, target_inds = ret_val
            training_pass(sess_docCNN, train_op, data_inds, target_inds, batch_target, placeholders, keep_prob)
            train_times.append(time.time() - t1)

            if i % 100 == 0:
                feed_dict = {indices_data_placeholder: data_inds, indices_target_placeholder: target_inds,
                             target_place_holder: batch_target, keep_prob_placeholder: 1}
                loss_out = sess_docCNN.run([loss], feed_dict)
                print('Iteration: {}, batch: {}, loss: {}'.format(itr, i, loss_out))
                print('Average train time: {:.5f}'.format(np.mean(train_times)))
                print('-----------------------------------------------')
                train_times = []

        print('overall highest accuracy: {}'.format(overall_highest))

        # Training the classifier from scratch.
        if itr > 0 and itr % 10 == 0:
            print('training a new classifier')
            # Forward pass to get the embeddings
            sess_classifier.run(train_init_op_classifier)
            train_data_size = len(train_data_indices_sup)
            test_data_size = len(test_data_indices_sup)

            train_data_doc2vec_sup = np.zeros([train_data_size, embed_dim])
            test_data_doc2vec_sup = np.zeros([test_data_size, embed_dim])

            for i in range(train_data_size):
                classifier_train_inds = np.expand_dims(train_data_indices_sup[i], axis=0)

                feed_dict_train = {indices_data_placeholder: classifier_train_inds, keep_prob_placeholder: 1}
                train_doc2vec = sess_docCNN.run(test_obj_cal_output, feed_dict_train)
                train_data_doc2vec_sup[i, :] = train_doc2vec

            for i in range(test_data_size):
                classifier_test_data = np.expand_dims(test_data_indices_sup[i], axis=0)

                feed_dict_test = {indices_data_placeholder: classifier_test_data, keep_prob_placeholder: 1}
                test_doc2vec = sess_docCNN.run(test_obj_cal_output, feed_dict_test)
                test_data_doc2vec_sup[i, :] = test_doc2vec

            acc_test_best = 0

            classifier_train_num_batch = train_data_size / batch_size
            classifier_test_num_batch = test_data_size / batch_size

            for classifier_iter in range(classifier_max_iter):
                classifier_train_shuffle_index = np.random.permutation(train_data_size)
                acc_train = 0
                acc_test = 0
                loss_out = 0

                for i in range(classifier_train_num_batch):
                    index = classifier_train_shuffle_index[
                        np.arange(i * batch_size, min((i + 1) * batch_size, train_data_size))]

                    classifier_train_inds = train_data_doc2vec_sup[index, :]
                    classifier_train_labels = train_labels_sup[index]

                    feed_dict_train = {classifier_data_place_holder: classifier_train_inds,
                                       classifier_label_place_holder: classifier_train_labels}
                    _, _acc_train, _loss_out = sess_classifier.run(
                        [classifier_train_op, train_accuracy_op, classifier_loss_op], feed_dict_train)

                    loss_out += _loss_out
                    acc_train += _acc_train

                for i in range(classifier_test_num_batch):
                    index = np.arange(i * batch_size, min((i + 1) * batch_size, test_data_size))
                    classifier_test_data = test_data_doc2vec_sup[index, :]
                    classifier_test_labels = test_labels_sup[index]
                    feed_dict_test = {classifier_data_place_holder: classifier_test_data,
                                      classifier_label_place_holder: classifier_test_labels}
                    _acc_test = sess_classifier.run([test_accuracy_op], feed_dict_test)

                    if isinstance(_acc_test, list):
                        _acc_test = _acc_test[0]
                    acc_test += _acc_test

                train_accuracy = acc_train / classifier_train_num_batch
                test_accuracy = acc_test / classifier_test_num_batch
                print('iter: {}, loss: {}, train accuracy: {}, test accuracy: {}'.
                      format(classifier_iter, loss_out, train_accuracy, test_accuracy))
                if test_accuracy > acc_test_best:
                    acc_test_best = test_accuracy
            print('best test acc is: {}'.format(acc_test_best))
            if acc_test_best > overall_highest:
                overall_highest = acc_test_best

        if itr % 10 == 0 and itr > 0:
            print('Saving model at {}'.format(itr))
            saver.save(sess_docCNN, os.path.join(checkpoint_path, 'model'), global_step=itr)
        itr += 1


if __name__ == '__main__':

    # command line tools for specifying the hyper-parameters and other training options.
    parser = argparse.ArgumentParser(description='Train a CNN for embedding learning.')
    parser.add_argument('--context-len', default=10, type=int, help='The size of the minimum context.')
    parser.add_argument('--batch-size', default=100, type=int, help='Batch size.')
    parser.add_argument('--num-filters', type=int, help='Number of convolutional filters.')
    parser.add_argument('--num-layers', type=int, help='Number of layers, including the last fully-connected layer.')
    parser.add_argument('--num-positive-words', type=int, help='Number of next words to predict.')
    parser.add_argument('--num-negative-words', type=int, help='Number of negative samples.')
    parser.add_argument('--num-residual', type=int, default=-1, help='Number of layers to skip in residual connections.')
    parser.add_argument('--num-classes', type=int, default=2,
                        help='Number of classes in the classifier (2 or 5). For IMDB, the number classes is only 2.')
    parser.add_argument('--dropout-keep-prob', type=float, default=0.8, help='The dropout keep prob.')
    parser.add_argument('--preprocessing', action='store_true',
                        help='If true, redo the pre-processing. Otherwise, load the saved pre-processed files.')
    parser.add_argument('--cache-dir', type=str, default='./cache',
                        help='The directory containing the saved pre-processed and embedding files')
    parser.add_argument('--dataset', type=str, required=True, help='The dataset to use, either \'amazon\' or \'imdb\'.')
    parser.add_argument('--data-dir', type=str, required=True, help='Directory containing the data.')
    parser.add_argument('--checkpoint-dir', type=str, default='./latest_model/', help='Checkpoints directory.')
    parser.add_argument('--model', type=str, default='CNN_pad',
                        help='The model to use, which is \'CNN_pad\', \'CNN_pool\' or \'CNN_topk\'')
    parser.add_argument('--embed-dim', type=int, default=300, help='The dimensionality of the word embeddings.')
    parser.add_argument('--learning-rate', type=float, default=0.0003, help='The learning rate.')
    parser.add_argument('--top-k', type=int, default=0, help='The value of k when performing k-max pooling')
    parser.add_argument('--max-iter', type=int, default=100, help='The maximum number of training iterations.')

    args = parser.parse_args()
    main(args)