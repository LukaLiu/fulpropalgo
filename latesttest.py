from NewMesgNode import AlgoNode, Pipe
import simpy
import simpy.rt
import time
import numpy as np
from sample_block_delay import generate_block_delays, generate_message_delays
from networkgraph import generate_graph, Node
from processdelaycsv import gen_delay_map


def simu(num_nodes):

	delay_map = gen_delay_map()

	env = simpy.Environment()
	nodes = []
	print('initialize network')
	nodesid = [i for i in range(0,num_nodes)]
	block_delays = generate_block_delays(num_nodes)
	for nid in nodesid:
		newNode = AlgoNode(env,nid,True,2000)
		newNode.set_block_delay(block_delays[nid])
		nodes.append(newNode)

	print('network created')
	total_t = 10000000000
	for node in nodes:
		tokens = total_t/num_nodes
		node.add_tokens(tokens)
	

	time1 = time.time()
	for node in nodes:
									#600000000
		node.chain.set_total_toknes(total_t)
		mdelay = generate_message_delays(num_nodes)
		ids = [x for x in range(0,num_nodes)]
		ids.pop(node.id)
		env.process(node.FixedGenerator())
		np.random.shuffle(mdelay)
		for id in ids:
			randdelay = mdelay[id]
			env.process(nodes[id].GossipReceiver(node.Connect(Pipe(env,randdelay))))

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

simu(400)

