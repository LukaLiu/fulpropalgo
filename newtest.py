from NewMesgNode import AlgoNode, Pipe
import simpy
import simpy.rt
import time
import random
from sample_block_delay import generate_block_delays
import pysnooper
from SortitionNode import AlgoNode as Proposer
from Message import Message
import networkx
from networkgraph import generate_graph, Node
from processdelaycsv import gen_delay_map
import os



def simu(num_nodes):

	delay_map = gen_delay_map()
	
	env = simpy.Environment()

	ct_tags = [i for i in range(0,28)]

	nodes = []
	print('initialize network')
	graph_nodes = generate_graph(num_nodes,8)
	filename=f'Netgraph.txt'
	file_path = 'RoundStatus/' + filename
	dirpath = os.path.dirname(os.path.abspath(__file__))
	folder_path = os.path.join(dirpath, file_path)
	with open(folder_path,"a+") as f:
		for node in graph_nodes:
			f.write(f'{node.id},{node.peers} \n')
	print('network created')
	block_delays = generate_block_delays(num_nodes)
	filename=f'blockdelays.txt'
	delay_path = 'RoundStatus/'+filename
	dirpath='/scratch/yliu7'
	folder_path = os.path.join(dirpath, delay_path)
	with open(folder_path,"a+") as f:
		for delay in block_delays:
			
			f.write(f'{delay} \n')
	
	for node in graph_nodes:
		
		newNode = AlgoNode(env,node.id,True,80)

		#
		#ct_tag = random.sample(ct_tags[0:1],1)[0]
		ct_tag = 1
		#ct_tag = 1
		newNode.tag_as_ct(ct_tag)
		min_delay=int(block_delays[node.id])
		newNode.set_block_delay(min_delay)


		for pid in node.peers:

			newNode.peers.append(pid)
		nodes.append(newNode)



	print('network created')
	total_t = 10000000000
	for node in nodes:
		tokens=total_t/num_nodes
		node.add_tokens(tokens)
		

	time1 = time.time()
	for node in nodes:
		total = total_t					#9800000
		node.chain.set_total_toknes(total)
		env.process(node.FixedGenerator())
		for peerid in node.peers:

			source_ct = node.ct_tag

			detination = nodes[peerid].ct_tag

			delay = delay_map[source_ct][detination]

			env.process(nodes[peerid].GossipReceiver(node.Connect(Pipe(env,delay))))

	env.run(until=None)
	time2=time.time()
	flag=True
	print(f'total time cost {time2-time1}')
	for node in nodes:
		for n in nodes:
			if node.id !=n.id:
				for round in range(1,2):
					if node.chain.chain[round].block_hash!=n.chain.chain[round].block_hash:
						print('different ledger detected')
						print(f'the differen bhash are {node.chain.chain[round].block_hash} and {n.chain.chain[round].block_hash}')
						flag =False
	if flag:
		print('no diverge found')

	for node in nodes:
		print(f'node {node.id} gossiped {len(node.Gossiped_Msg)} msgs')

	total = 0
	for node in nodes:
		total+=node.counttime
	print('total time to count ', total)

simu(500)


