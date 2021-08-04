import hashlib
import os
import pickle

FOLDER = '.cache'
os.makedirs(FOLDER, exist_ok=True)


def cache(function):
    """
    Cache the result of a function in disk
    """
    def modified(*args):
        args_id = hashlib.sha256(str(args).encode()).hexdigest()[:16]
        name = str(function.__name__) + '.' + args_id + '.pickle'
        path = os.path.join(FOLDER, name)
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
                return data
        else:
            data = function(*args)
            with open(path, 'wb') as f:
                pickle.dump(data, f)
            return data
    return modified
