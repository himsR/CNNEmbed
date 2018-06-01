import os
import cPickle
import nltk
import struct
import numpy as np
from scipy.io import loadmat
import glob
import cPickle
import pdb


def tokenize_sentence(data, data_type, word_to_index, max_doc_len, fixed_length):
    """
    Convert data, an array containing IMDB sentiment data, into a list of indices into the word2vec matrix.

    Args:
        data: An array containing the IMDB sentiment data, as unicode strings.
        data_type (str): Data to use, 'imdb', 'amazon', or 'wikipedia'
        word_to_index (dict): Dict that maps words to their index in the word2vec matrix
        max_doc_len (int): Maximum length of input, if using CNN-pad
        fixed_length (bool): True if using CNN-pad

    Returns:
        tokenized (list): list of lists, where each list is a document from the IMDB data converted to their word2vec
            indices
    """

    tokenized = []
    tknzr = nltk.tokenize.TweetTokenizer()

    for sentence in data:
        if data_type == 'imdb':
            sentence = sentence[0][0]
            tokens = nltk.word_tokenize(sentence)
        elif data_type == 'amazon':
            tokens = nltk.word_tokenize(' '.join(tknzr.tokenize(sentence)))
        else:
            tokens = nltk.word_tokenize(' '.join(tknzr.tokenize(sentence.decode('latin-1'))))

        tokenized_sentence = [word.lower() for word in tokens]
        tokenized_sentence = [word for word in tokenized_sentence if word in word_to_index]
        index_list = [word_to_index[word] for word in tokenized_sentence]
        length = len(index_list)
        if fixed_length and length > max_doc_len:
            index_list = index_list[:max_doc_len]

        tokenized.append(index_list)

    return tokenized


def tokenize_sentence_wikipedia(data, word_embeddings, word_to_index, max_doc_len, fixed_length):
    """
    Tokenizing the sentence specifically for the Wikipedia data. This is more difficult.

    :param data:
    :param word_embeddings:
    :param word_to_index:
    :param max_doc_len:
    :param fixed_length:
    :return:
    """

    tokenized = []
    freqs = dict()
    tknzr = nltk.tokenize.TweetTokenizer()

    for sentence in data:
        tokens = nltk.word_tokenize(' '.join(tknzr.tokenize(sentence.decode('latin-1'))))
        tokens = [word.lower() for word in tokens]

        for tok in tokens:
            if tok in freqs:
                freqs[tok] += 1
            else:
                freqs[tok] = 1

        tokenized.append(tokens)

    # We only keep tokens that have appeared at least 10 times in the data and map everything else to <unk>.
    converted_to_indices = []
    word_to_index['<unk>'] = word_embeddings.shape[0]
    curr_ind = word_embeddings.shape[0] + 1
    num_new_tokens = 1
    for tokens in tokenized:
        indexed_sen = []
        for tok in tokens:
            if freqs[tok] >= 9:
                if tok in word_to_index:
                    indexed_sen.append(word_to_index[tok])
                else:
                    word_to_index[tok] = curr_ind
                    indexed_sen.append(curr_ind)
                    curr_ind += 1
                    num_new_tokens += 1
            else:
                indexed_sen.append(word_to_index['<unk>'])

        if fixed_length and len(indexed_sen) > max_doc_len:
            indexed_sen = indexed_sen[:max_doc_len]

        converted_to_indices.append(indexed_sen)

    word_embeddings = np.vstack((word_embeddings, np.random.uniform(-1, 1, size=[num_new_tokens, 300])))
    return converted_to_indices, word_embeddings, word_to_index


def load_word2vec(data_path):
    """
    Load the pre-trained word2vec vectors and return them, along with a mapping from words to their index in word2vec.

    Args:
        data_path (str): Path to the directory containing word2vec

    Returns:
        word_vectors (numpy.ndarray): Array of pre-trained word2vec vectors.
        word_to_index (dict): Mapping from words in word2vec to their index in word_vectors.
    """

    word2vec_f = open(os.path.join(data_path, 'word2vec/GoogleNews-vectors-negative300.bin'), 'rb')

    c = None
    # read the header
    header = ''
    while c != '\n':
        c = word2vec_f.read(1)
        header += c

    num_vectors, vector_len = (int(x) for x in header.split())
    word_vectors = np.zeros((num_vectors, vector_len))
    word_to_index = dict()
    float_size = 4  # 32bit float

    for n in range(num_vectors):
        word = []
        c = word2vec_f.read(1)
        while c != ' ':
            word.append(c)
            c = word2vec_f.read(1)
        word = ''.join(word).strip()

        binary_vector = word2vec_f.read(float_size * vector_len)
        vec = [struct.unpack_from('f', binary_vector, i)[0] for i in xrange(0, len(binary_vector), float_size)]
        word_vectors[n, :] = np.array(vec)
        word_to_index[word] = n

    return word_vectors, word_to_index


def load_word2vec_fast(data_path):
    '''
    Loading the .mat version of work2vec, which is way faster. Won't be committing this.
    '''

    word_vectors = loadmat(os.path.join(data_path, 'word2vec/GoogleNews-vectors-negative300.mat'))
    word_vectors = word_vectors['vectors']

    dict_file = open(os.path.join(data_path, 'word2vec/dict.txt'), 'r')
    word_to_index = dict()
    i = 0
    line = dict_file.readline()
    while line != '':
        word_to_index[line.strip()] = i
        i += 1
        line = dict_file.readline()
    dict_file.close()
    return word_vectors, word_to_index


def get_data_imdb(data_path, max_doc_len, fixed_length=True):
    """
    Return the IMDB test and training data as a list of lists of indices.

    Args:
        data_path (str): Path to the directory containing the data.
        max_doc_len (int): Maximum length of input, if using CNN-pad
        fixed_length (bool): True if using CNN-pad

    Returns:
        input_embeddings (numpy.ndarray): Input word embeddings to the CNN
        train_data_indices (list): list of list of indices to word2vec, for training
        train_labels (numpy.ndarray): 1D array of labels, for training
        test_data_indices (list): list of list of indices to word2vec, for testing
        test_labels (numpy.ndarray): 1D array of labels, for training
    """

    # Read pre-trained word2vec vectors and dictionary
    word_vectors, word_to_index = load_word2vec_fast(data_path)

    # Read train test data and label
    temp = loadmat(os.path.join(data_path, 'imdb_sentiment/imdb_sentiment.mat'))
    train_data = temp['train_data']
    test_data = temp['test_data']
    train_labels = temp['train_labels']
    test_labels = temp['test_labels']

    print('Tokenizing data and converting to indices.')
    train_data_indices = tokenize_sentence(train_data, 'imdb', word_to_index, max_doc_len, fixed_length)
    test_data_indices = tokenize_sentence(test_data, 'imdb', word_to_index, max_doc_len, fixed_length)

    # Create the unique word dict used by the model
    flatten_train = [item for sublist in train_data_indices for item in sublist]
    train_data_indices_unique = list(set(flatten_train))

    flatten_test = [item for sublist in test_data_indices for item in sublist]
    test_data_indices_unique = list(set(flatten_test))

    train_data_indices_unique.extend(test_data_indices_unique)
    all_unique_indices = list(set(train_data_indices_unique))

    reverse_index = {}
    for i in range(len(all_unique_indices)):
        reverse_index[all_unique_indices[i]] = i

    input_embeddings = word_vectors[all_unique_indices]
    # add an empty to vector and reverse vector
    input_embeddings = np.vstack([input_embeddings, np.zeros(input_embeddings.shape[1])])
    reverse_index[-1] = input_embeddings.shape[0] - 1
    print('Number of unique words in this dataset is {}'.format(len(input_embeddings)))

    for i in range(len(train_data_indices)):
        for j in range(len(train_data_indices[i])):
            train_data_indices[i][j] = reverse_index[train_data_indices[i][j]]
    for i in range(len(test_data_indices)):
        for j in range(len(test_data_indices[i])):
            test_data_indices[i][j] = reverse_index[test_data_indices[i][j]]

    # Convert list to np array
    train_data_indices = np.array(train_data_indices)
    train_labels = np.array(train_labels)
    test_data_indices = np.array(test_data_indices)
    test_labels = np.array(test_labels)

    return input_embeddings, train_data_indices, train_labels, test_data_indices, test_labels


def get_data_amazon(data_path, max_doc_len, fixed_length=True):
    """
    Return the Amazon Fine Food Reviews test and training data as a list of lists of indices.

    Args:
        data_path (str): Path to the directory containing the data.
        max_doc_len (int): Maximum length of input, if using CNN-pad
        fixed_length (bool): True if using CNN-pad

    Returns:
        input_embeddings (numpy.ndarray): Input word embeddings to the CNN
        train_data_indices (list): list of list of indices to word2vec, for training
        train_labels (numpy.ndarray): 1D array of labels, for training
        test_data_indices (list): list of list of indices to word2vec, for testing
        test_labels (numpy.ndarray): 1D array of labels, for training
    """

    # Read pre-trained word2vec vectors and dictionary
    word_vectors, word_to_index = load_word2vec_fast(data_path)

    with open(os.path.join(data_path, 'amazon_food/amazon_train_data.pkl')) as train_data_fn:
        train_data = cPickle.load(train_data_fn)

    with open(os.path.join(data_path, 'amazon_food/amazon_test_data.pkl')) as test_data_fn:
        test_data = cPickle.load(test_data_fn)

    train_text = train_data[0]
    train_score = train_data[1]
    test_text = test_data[0]
    test_score = test_data[1]
    all_text = train_text + test_text

    data_indices = tokenize_sentence(all_text, 'amazon', word_to_index, max_doc_len, fixed_length)
    # Create the unique word dict used by the model
    flatten_data = [item for sublist in data_indices for item in sublist]
    all_unique_indices = list(set(flatten_data))

    reverse_index = {}
    for i in range(len(all_unique_indices)):
        reverse_index[all_unique_indices[i]] = i

    input_embeddings = word_vectors[all_unique_indices]
    # add an empty to vector and reverse vector
    input_embeddings = np.vstack([input_embeddings, np.zeros([input_embeddings.shape[1]])])
    reverse_index[-1] = input_embeddings.shape[0] - 1
    print('Number of unique words in this dataset is {}'.format(len(input_embeddings)))

    # Convert index from whole vocabulary to local vocabulary
    for i in range(len(data_indices)):
        for j in range(len(data_indices[i])):
            data_indices[i][j] = reverse_index[data_indices[i][j]]
    data_indices = np.array(data_indices)

    train_data_indices = data_indices[:80000]
    train_labels = np.array(train_score)
    train_labels -= 1

    test_data_indices = data_indices[80000:]
    test_labels = np.array(test_score)
    test_labels -= 1

    return input_embeddings, train_data_indices, train_labels, test_data_indices, test_labels


def get_data_wikipedia(data_path, max_doc_len, fixed_length=True):
    """
    Return the Wikipedia test and training data as a list of lists of indices.

    Args:
        data_path (str): Path to the directory containing the data.
        max_doc_len (int): Maximum length of input, if using CNN-pad
        fixed_length (bool): True if using CNN-pad

    Returns:
        input_embeddings (numpy.ndarray): Input word embeddings to the CNN
        train_data_indices (list): list of list of indices to word2vec, for training
        train_labels (numpy.ndarray): 1D array of labels, for training
        test_data_indices (list): list of list of indices to word2vec, for testing
        test_labels (numpy.ndarray): 1D array of labels, for training
    """

    # Documents that have length zero, after filtering out words not in word2vec. We'll keep these for now.
    skip_inds = [114767, 136434, 181703, 301236, 55718, 56001, 72101, 99528]

    # Read pre-trained word2vec vectors and dictionary
    word_vectors, word_to_index = load_word2vec_fast(data_path)
    data_file = open(os.path.join(data_path, 'wikipedia_100/alldata.txt'), 'r')
    labels_file = open(os.path.join(data_path, 'wikipedia_100/alldata-label.txt'), 'r')
    train_data = []
    train_labels = []
    test_data = []
    test_labels = []

    line_num = 1
    text_line = data_file.readline()
    label_line = labels_file.readline()
    while text_line != '':
        if line_num <= 10000:
            train_data.append(text_line.strip())
            train_labels.append(int(label_line.strip()))
        elif line_num <= 100000:
            test_data.append(text_line.strip())
            test_labels.append(int(label_line.strip()))
        else:
            train_data.append(text_line.strip())
            train_labels.append(-1)

        text_line = data_file.readline()
        label_line = labels_file.readline()
        line_num += 1

    all_text = train_data + test_data
    data_indices, word_vectors, word_to_index = tokenize_sentence_wikipedia(all_text, word_vectors, word_to_index,
                                                                            max_doc_len, fixed_length)
    # Create the unique word dict used by the model
    flatten_data = [item for sublist in data_indices for item in sublist]
    all_unique_indices = list(set(flatten_data))

    reverse_index = {}
    for i in range(len(all_unique_indices)):
        reverse_index[all_unique_indices[i]] = i

    input_embeddings = word_vectors[all_unique_indices]
    # add an empty to vector and reverse vector
    input_embeddings = np.vstack([input_embeddings, np.zeros([input_embeddings.shape[1]])])
    reverse_index[-1] = input_embeddings.shape[0] - 1
    print('Number of unique words in this dataset is {}'.format(len(input_embeddings)))

    # Convert index from whole vocabulary to local vocabulary
    for i in range(len(data_indices)):
        for j in range(len(data_indices[i])):
            data_indices[i][j] = reverse_index[data_indices[i][j]]
    data_indices = np.array(data_indices)

    # remap the labels.
    all_labels = list(set(test_labels))
    all_labels.sort()
    class_map = dict()

    ind = 0
    for c in all_labels:
        class_map[c] = ind
        ind += 1
    class_map[-1] = -1

    # The first 100,000 data points are labelled data, rest is unlabelled
    train_data_indices = data_indices[:-90000]
    train_labels = np.array([class_map[x] for x in train_labels])
    test_data_indices = data_indices[-90000:]
    test_labels = np.array([class_map[x] for x in test_labels])

    return input_embeddings, train_data_indices, train_labels, test_data_indices, test_labels


def get_data_gbw(data_path, max_doc_len=None):
    '''
    Turn the GBW dataset into a list of indices. Store the indices locally.

    Args:
        data_path (str): Path to the directory containing the data.
        max_doc_len (int): Maximum length of input, if using CNN-pad. None, otherwise.
    '''

    word_vectors, word_to_index = load_word2vec_fast(data_path)
    all_inds = []
    new_word_to_index = dict()
    for word in word_to_index:
        if word.lower() in new_word_to_index:
            continue
        elif word.lower() in word_to_index:
            new_word_to_index[word.lower()] = word_to_index[word.lower()]
            all_inds.append(new_word_to_index[word.lower()])

    all_inds.sort()
    new_ind_mapping = dict()
    i = 0
    for ind in all_inds:
        new_ind_mapping[ind] = i
        i += 1

    word_vectors = word_vectors[all_inds, :]
    word_to_index = dict()
    for elem in new_word_to_index:
        word_to_index[elem] = new_ind_mapping[new_word_to_index[elem]]
    print('Size of the vocabulary: {}'.format(word_vectors.shape[0]))

    # Adding <unk> token
    word_vectors = np.vstack((word_vectors, np.random.uniform(-1, 1, size=[1, 300])))
    word_to_index['<unk>'] = len(word_to_index)

    # Adding zero vector
    word_vectors = np.vstack([word_vectors, np.zeros([word_vectors.shape[1]])])

    # Saving the embeddings
    np.save('./gbw_cache/vector_up.npy', word_vectors)
    with open('./gbw_cache/word_to_index.pkl', 'w') as f:
        cPickle.dump(word_to_index, f)

    # rather than remap the vocabulary to a smaller, because the dataset is so large, I'll just store the entire
    # word2vec vocabulary. The amount of memory saved is probably insignificant, after removing duplicates after
    # converting to lowercase.
    gbw_files = glob.glob(os.path.join(data_path, 'gbw/training-monolingual.tokenized.shuffled/*'))
    tknzr = nltk.tokenize.TweetTokenizer()
    lengths = []
    file_num = 1
    for fn in gbw_files:
        token_fn = os.path.join(data_path, 'gbw/tokenized', fn.split('/')[-1] + '.npy')
        all_docs = []
        with open(fn, 'r') as f:
            for line in f:
                # use tokenizer here
                tokens = nltk.word_tokenize(' '.join(tknzr.tokenize(line)))
                tokens = [word.lower() for word in tokens]
                line_tok = []
                for word in tokens:
                    if word in word_to_index:
                        line_tok.append(word_to_index[word])
                    else:
                        line_tok.append(word_to_index['<unk>'])

                if max_doc_len is not None and len(line_tok) > max_doc_len:
                    line_tok = line_tok[:max_doc_len]

                if len(line_tok) > 0:
                    all_docs.append(line_tok)
                    lengths.append(len(line_tok))

        np.save(token_fn, all_docs)
        print('Finished file {} of 100'.format(file_num))
        file_num += 1

    return lengths


if __name__ == '__main__':

    get_data_gbw('/home/shunan/Data/')
