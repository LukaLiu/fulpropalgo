import numpy as np
import os



def generate_block_delays(num_nodes):
	dirpath = os.path.dirname(os.path.abspath(__file__))
	filepath = 'delaydatas/bitcoinblockdelay.csv'
	folder_path = os.path.join(dirpath, filepath)

	btc_data = np.genfromtxt(folder_path, delimiter=',')

	delays = [i for i in range(0, 30000)]
	probs = [btc_data[i][3] for i in delays]
	freq = [btc_data[i][2] for i in delays]

	total=0
	for f in freq:
		total+=f
	probs=[f/total for f in freq]

	samples = np.random.choice(delays, num_nodes, replace=True, p=probs)
	samples = np.divide(samples,10)
	samples = np.around(samples)
	samples = np.multiply(samples,10)
	return samples


def generate_message_delays(num_nodes):
	num_nodes = num_nodes
	dirpath = os.path.dirname(os.path.abspath(__file__))
	filepath = 'delaydatas/transdelay.csv'
	folder_path = os.path.join(dirpath, filepath)

	btc_data = np.genfromtxt(folder_path, delimiter=',')

	delays = [i for i in range(0, 2500)]
	probs = [btc_data[i][3] for i in delays]
	freq = [btc_data[i][2] for i in delays]

	total=0
	for f in freq:
		total+=f
	probs=[f/total for f in freq]

	samples = np.random.choice(delays, num_nodes, replace=True, p=probs)
	samples = np.divide(samples,10)
	samples = np.around(samples)
	samples = np.multiply(samples,10)

	return samples
