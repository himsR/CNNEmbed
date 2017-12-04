import numpy as np
import sys
import time

def pad_zeros(data_indices, zero_ind, max_doc_len):
    """
    Pad the indices with zero in the beginning if the length is less than max number of words.

    Args:
        data_indices

    """

    new_data_indices = []
    for doc in data_indices:
        if len(doc) < max_doc_len:
            doc = [zero_ind for _ in range(max_doc_len - len(doc))] + doc
        new_data_indices.append(doc)

    return np.array(new_data_indices)

def get_sup_data(vector_up, train_data_indices, test_data_indices, train_labels, test_labels,
                 unlabeled_class, split_class, fixed_length, max_doc_len, num_classes):
    """
    :return:
    """
    train_labels = train_labels.reshape([train_labels.shape[0]])
    test_labels = test_labels.reshape([test_labels.shape[0]])
    if num_classes == 2:
        I = train_labels != unlabeled_class
        J = test_labels != unlabeled_class
        train_data_indices_sup = train_data_indices[I]
        test_data_indices_sup = test_data_indices[J]
        if fixed_length:
            train_data_indices_sup = pad_zeros(train_data_indices_sup, vector_up.shape[0] - 1, max_doc_len)
            test_data_indices_sup = pad_zeros(test_data_indices_sup, vector_up.shape[0] - 1, max_doc_len)
        train_labels_sup = train_labels[I]
        test_labels_sup = test_labels[J]
        train_labels_sup = train_labels_sup >= split_class
        test_labels_sup = test_labels_sup >= split_class
    elif num_classes == 5:
        if fixed_length:
            train_data_indices_sup = pad_zeros(train_data_indices, vector_up.shape[0] - 1, max_doc_len)
            test_data_indices_sup = pad_zeros(test_data_indices, vector_up.shape[0] - 1, max_doc_len)
        else:
            train_data_indices_sup = np.copy(train_data_indices)
            test_data_indices_sup = np.copy(test_data_indices)
        train_labels_sup = np.copy(train_labels)
        test_labels_sup = np.copy(test_labels)
    else:
        print("Number of classes has to be 2 or 5!")
        sys.exit()

    return train_data_indices_sup, test_data_indices_sup, train_labels_sup, test_labels_sup


class BatchGeneratorSample(object):
    '''
    Class for generating batches of data, but subsample the training data.
    '''

    def __init__(self, training_inds, num_pos_exs, num_neg_exs, max_doc_len, context_len, vocab_size,
                 batch_size):

        self.num_pos_exs = num_pos_exs
        self.num_neg_exs = num_neg_exs
        self.max_doc_len = max_doc_len
        self.context_len = context_len
        self.vocab_size = vocab_size
        self.batch_size = batch_size
        self.queue_len = 10
        self.counter = 0
        self.queue = []

        # Remove the documents that are too short.
        self.training_inds = self.remove_short_docs(training_inds)

    def get_data_size(self):
        '''
        Return the size of the training data.
        '''

        return len(self.training_inds)

    def remove_short_docs(self, training_inds):
        '''
        Remove the documents from the training indices that are less than the context length.
        '''

        skipped_docs = 0
        new_train_inds = []
        for doc in training_inds:
            if len(doc) >= self.num_pos_exs + 1:
                new_train_inds.append(doc)
            else:
                skipped_docs += 1

        print('Number of skipped documents: {}'.format(skipped_docs))
        return np.array(new_train_inds)

    def get_data(self):

        if len(self.queue) > 0:
            return self.queue.pop()
        elif len(self.queue) == 0 and self.counter + self.batch_size > len(self.shuffle_indices):
            return None

    def add_to_queue(self):

        if self.counter + self.batch_size <= len(self.shuffle_indices):
            inds = self.shuffle_indices[self.counter:self.counter + self.batch_size]
            self.queue.append((self.training_inds_with_samples[inds, :], self.target_with_samples[inds, :]))
            self.counter += self.batch_size

    def refill_queue(self):
        '''
        Refill the queue.
        '''

        self.training_inds_with_samples = []
        self.target_with_samples = []
        self.counter = 0

        t1 = time.time()
        # Generate all the batches here.
        num_resamples = 0
        for i in range(len(self.training_inds)):
            dat = self.training_inds[i]
            if len(dat) < self.context_len + self.num_pos_exs:
                pos_inds = dat[-self.num_pos_exs:]
                t_ind = len(dat) - self.num_pos_exs
                context_inds = set(dat)
            else:
                forward_inds = range(self.context_len, min(len(dat) - self.num_pos_exs + 1, self.max_doc_len))
                t_ind = np.random.choice(forward_inds)
                pos_inds = dat[t_ind:t_ind+self.num_pos_exs]
                context_inds = set(dat[:t_ind + self.num_pos_exs])

            # Doing the negative sampling.
            samples = np.random.choice(self.vocab_size - 1, size=self.num_neg_exs, replace=False)
            while context_inds.intersection(set(samples)):
                samples = np.random.choice(self.vocab_size - 1, size=self.num_neg_exs, replace=False)
                num_resamples += 1

            # Pad with zeros at the beginning
            tmp = dat[:t_ind]
            train_inds = [(self.vocab_size - 1) for _ in range(self.max_doc_len - len(tmp))] + tmp
            self.training_inds_with_samples.append(train_inds)
            self.target_with_samples.append(np.concatenate((pos_inds, samples)))

        self.training_inds_with_samples = np.array(self.training_inds_with_samples)
        self.target_with_samples = np.array(self.target_with_samples)

        # Shuffle the batches.
        self.shuffle_indices = np.random.permutation(self.training_inds_with_samples.shape[0])
        for i in range(self.queue_len):
            self.add_to_queue()

        print('Time spent generating all negative samples: {}'.format(time.time() - t1))
        print('Number of resamples: {}'.format(num_resamples))