import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from scipy import stats

if __name__ == '__main__':
    train_data = pd.read_csv('train.tsv', sep='\t', encoding='utf-8')
    test_data = pd.read_csv('test.tsv', sep='\t', encoding='utf-8')
