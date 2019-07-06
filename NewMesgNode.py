from BlockChain import BlockChain
import vrftool
import simpy
from utils import *
from Block import Block
from hashlib import sha256
from Message import Message
import time
import os

system_sk = b'413a67a03a4da74902bc061429a2a7b63425b55cad6f31ede3e6764c2374c8254265c247c6b2583b2c49a868c63b910181d315646d486e4b193d89a6152bf996'
system_pk = b'4265c247c6b2583b2c49a868c63b910181d315646d486e4b193d89a6152bf996'
NULL_HASH = 0x00.to_bytes(32, byteorder='little')
block_proposer = 'b'
committe_member = 'c'

BA_Thresh=2/3
Final_State = 'final'
Tenative_State = 'tenative'
proposer_probs = 50/10000
block_proposer_size = 26
time_out_block_proposal=2
time_out_step = 5
Reduction_one=1
Reduction_two=2


class Pipe(object):

	def __init__(self, env, delay, capacity = simpy.core.Infinity):

		self.env = env
		self.capacity = capacity
		self.delay = delay
		self.pipe = simpy.Store(self.env, self.capacity)

class AlgoNode(object):

	def __init__(self, env, id, honest, manual_committee_size=2000):
		self.env = env
		self.id = id
		self.chain=BlockChain()
		self.hashchain=dict()
		#store peer AlgoNode for shuffling
		self.peers=list()


		self.sk = vrftool.new_sk()
		self.pk= vrftool.get_pk(self.sk)

		#sortition parameters
		self.proposers = 26
		self.manual_committee_size = manual_committee_size

		self.Pipes=[]
		self.Gossiped_Msg=[]

		self.Max_Priority_Proposal=dict()
		self.block_candidates = dict()
		#buffer structure: round:messages
		self.Block_Proposals_Msg=dict()
		self.Vote_Msg =dict()
		self.voters=dict()
		self.vote_buffer=dict()
		self.wblock=dict()
		self.waiting_block =False
		self.SortForC= dict()
		self.SortForB=dict()
		self.Tenative = False
		self.ReductionTime=0
		self.BBAtime=0
		self.height = max(self.chain.chain.keys())
		self.counttime=0
		self.Round_start_time=dict()
		#set node type honest or malicious
		if honest:
			self.honest = True
		else:
			self.honest = False

	def set_block_delay(self,delay):
		self.block_delay = delay

	# def new_secret_key(self):
	# 	self.sk = vrftool.new_sk()
	def tag_as_ct(self,ct_tag):
		self.ct_tag = ct_tag

	def Connect(self, Pipe):

		self.Pipes.append(Pipe)

		return Pipe

	def Gossip_Msg(self, msg):

		if not self.Pipes:
			raise RuntimeError('There are no peer connected')

		events = [pipe.pipe.put(msg) for pipe in self.Pipes]

		return self.env.all_of(events)

	#give tokens to account
	def add_tokens(self, tokens):
		self.tokens = tokens

	#add id of new peer list, which is set as integer for convinient simulation
	def add_peers(self,id):
		if id not in self.peers:
			self.peers.append(id)



	def FixedGenerator(self):

		current_round = 1
		#manual size for committe size


		roundflag = True
		while roundflag:
			filename=f'{str(current_round)}roundRecord.txt'
			file_path = 'RoundStatus/' + filename
			dirpath='/scratch/yliu7/'
			folder_path = os.path.join(dirpath, file_path)
			if not self.Tenative and not self.waiting_block:
				self.Round_start_time[current_round] = self.env.now
				folder_path = os.path.join(dirpath, file_path)
				empty_block = self.generate_empty_block(current_round)

				proposer = self.Sortition(self.sk, current_round, block_proposer, block_proposer_size)

				if proposer:
					self.propose_block(proposer, current_round)
					print(f'node {self.id} sorted as proposer at time {self.env.now}')
					
					#to sendout block system sync useage,can be ignored

				else:
					self.Max_Priority_Proposal[current_round]=empty_block.priority
					self.block_candidates[current_round]=[empty_block]
				
			
				priority_delay = 5000
				timer = 0
			
				while timer <priority_delay:
					timer+=10
					yield self.env.timeout(10)


				proposal_waiting_timeout = 60000
				timer = 0


				max_prio_proposal = empty_block.block_hash
				
				#max_priority = self.Max_Priority_Proposal[current_round]
				
				while not self.check_proposal(current_round):
					if timer<proposal_waiting_timeout:
						timer+=10
						yield self.env.timeout(10)
					else:
						break
						
				max_priority = self.Max_Priority_Proposal[current_round]
				
				if self.check_proposal(current_round):
					for block in self.block_candidates[current_round]:
						if block.priority ==max_priority:
							max_prio_proposal=block.block_hash
							max_priority=block.priority
					



				maxprio=f'{str(current_round)}roundMaxp.txt'
				mfile_path = 'RoundStatus/' + maxprio
				dirpath='/scratch/yliu7/'
				max_path = os.path.join(dirpath, mfile_path)
				with open(max_path, 'a+') as mf:
					flag = True
					if max_priority==empty_block.block_hash:
						flag=False
					mf.write(f'{self.id},{current_round},{max_prio_proposal},{flag} \n')

				delay_left = 60000-timer

				ctx = self.get_ctx(current_round)
				print(f'node {self.id} starts ba at time {self.env.now}')
				
				BA_result = yield self.env.process(self.BA(ctx,current_round,max_prio_proposal,delay_left))
				print(f'ba result {BA_result[1]}')


				if BA_result[0]==Final_State:

					new_block_hash = BA_result[1]

					if new_block_hash==empty_block.block_hash:
						self.chain.chain[current_round]=empty_block
						with open(folder_path, 'a+') as f:
							f.write(f'{current_round},{self.id},final,{self.env.now},{self.env.now-self.Round_start_time[current_round]},{empty_block.block_hash},{False} \n')
						
						
						print(
							f'Round {current_round} node {self.id} reaches final with emptyblock cost {self.env.now-self.Round_start_time[current_round]} \n')
						
						self.Gossiped_Msg.clear()
						
						current_round+=1
						
						
						
					else:

						#if self.block_candidates[current_round].block_hash==new_block_hash:
						newb =  self.fetch_proposal(current_round, new_block_hash)
						if newb:
							self.chain.chain[current_round]=newb
							folder_path = os.path.join(dirpath, file_path)
							with open(folder_path, 'a+') as f:
								f.write(
									f'{current_round},{self.id},final,{self.env.now},{self.env.now-self.Round_start_time[current_round]},{new_block_hash},{True} \n')
							
							current_round += 1
							self.Gossiped_Msg.clear()
					
						else:
							self.waiting_block=True
							self.wblock[current_round]=new_block_hash
							folder_path = os.path.join(dirpath, file_path)
							with open(folder_path, 'a+') as f:
								f.write(
									f'{current_round},{self.id},finalw,{self.env.now},{self.env.now-self.Round_start_time[current_round]},{new_block_hash},{True} \n')
							

				elif BA_result[0] == Tenative_State:
					self.Tenative=True
					bhash =BA_result[1]
					folder_path = os.path.join(dirpath, file_path)
					with open(folder_path, 'a+') as f:
						f.write(f'{current_round},{self.id},tenative,{self.env.now},{self.env.now-self.Round_start_time[current_round]},{bhash},{(not bhash==empty_block.block_hash)} \n')
					
					print(f'node {self.id} reches tenative state and needs more count result')

			elif self.waiting_block:

				folder_path = os.path.join(dirpath, file_path)

				waiting_hash = self.wblock[current_round]
				timer = 0
				while timer<5000 and not self.fetch_proposal(current_round,waiting_hash):
					timer+=10
					yield self.env.timeout(timer)
				newb = self.fetch_proposal(current_round,waiting_hash)
				if newb:
					self.waiting_block=False
					self.chain.chain[current_round]=newb

					with open(folder_path,'a+') as f:
						f.write(f'{current_round},{self.id},final,{self.env.now},{self.env.now-self.Round_start_time[current_round]},{newb.block_hash,}{True} \n')
					
					current_round += 1
					self.Gossiped_Msg.clear()
					
				else:
					continue
							
			elif self.Tenative:
				empty_block=self.generate_empty_block(current_round)
				yield self.env.timeout(10)
				max_step = 5000
				step = 0
				while not self.CountVotes(ctx, current_round, step=Final_State):
					if step < max_step:
						step += 100
						yield self.env.timeout(100)
					else:
						break
				r = self.CountVotes(ctx, current_round, Final_State)
				if r:
					if r==empty_block.block_hash:
						self.chain.chain[current_round]=empty_block
						folder_path = os.path.join(dirpath, file_path)
						with open(folder_path, 'a+') as f:
							f.write(
								f'{current_round},{self.id},final,{self.env.now},{self.env.now-self.Round_start_time[current_round]},{empty_block.block_hash},{False} \n')

						
						
						self.Gossiped_Msg.clear()
						
						current_round += 1
						self.Tenative=False
						
						
					else:
						newb = self.fetch_proposal(current_round,r)
						if newb:
							self.Tenative=False
							self.chain.chain[current_round]=newb
							with open(folder_path,'a+') as f:
								f.write(f'{current_round},{self.id},final,{self.env.now},{self.env.now-self.Round_start_time[current_round]},{newb.block_hash,}{True} \n')
							
							current_round+=1
							self.Gossiped_Msg.clear()
							
						else:
							self.Tenative=False
							self.waiting_block=True
							self.wblock[current_round]=r
							with open(folder_path,'a+') as f:
								f.write(
									f'{current_round},{self.id},finalw,{self.env.now},{self.env.now-self.Round_start_time[current_round]},{r}{True} \n')
			if current_round == 15:

				roundflag =False

	#connect new peers, add pipes to output conn in simpy
	# Simpy Msg receiver
	def GossipReceiver(self, inpipe):


		while True:


			msg = yield inpipe.pipe.get()
			mes_type = msg[0]
			if mes_type=='b' or mes_type=='p':
				round = msg[1]
			else:
				round = msg[1][0]
			if round<self.height:
				continue
			elif mes_type == 'b':
				round = msg[1]
				msg_id=msg[0]+str(round)+msg[2].block_hash+msg[2].priority

				block_proposal=msg[2]
				priority = block_proposal.priority
				#print(f'node has proposale msg at time {self.env.now}')

				if msg_id not in self.Gossiped_Msg:
					self.Gossiped_Msg.append(msg_id)
					#self.Gossip_Msg(msg)


					#currently 1mb block assum 10sec delay
					if round not in self.block_candidates.keys():
						self.block_candidates[round]=[]

					if round not in self.Max_Priority_Proposal.keys():
						# block download delay
						self.Max_Priority_Proposal[round]=block_proposal.priority
						delay = self.block_delay
						timer = 0
						while timer < delay:
							timer += 10
							yield self.env.timeout(10)
						self.block_candidates.setdefault(round,[]).append(block_proposal)
						
							
						if block_proposal.priority>self.Max_Priority_Proposal[round]:
							self.Max_Priority_Proposal[round]=block_proposal.priority
						else:
							continue


					if priority==self.Max_Priority_Proposal[round] or priority>self.Max_Priority_Proposal[round]:
						#block download delay
						delay = self.block_delay
						timer = 0
						while timer < delay:
							timer += 10
							yield self.env.timeout(10)
						
						if block_proposal.priority==self.Max_Priority_Proposal[round]:
							self.block_candidates.setdefault(round,[]).append(block_proposal)
						elif block_proposal.priority>self.Max_Priority_Proposal[round]:
							self.block_candidates.setdefault(round,[]).append(block_proposal)
							self.Max_Priority_Proposal[round]=block_proposal.priority
							

					else:
						continue


				else:
					continue


			elif mes_type=='p':

				round = msg[1]
				block_hash=msg[2]
				priority = msg[3]
				msg_id = 'p'+msg[0]+str(round)+block_hash+priority

				if msg_id not in self.Gossiped_Msg:
					self.Gossiped_Msg.append(msg_id)
					#self.Gossip_Msg(msg)
					delay = inpipe.delay
					yield self.env.timeout(5)
					timer = 0
					while timer < delay:
						timer+=5
						yield self.env.timeout(5)
					
					if round not in self.Max_Priority_Proposal.keys():
						self.Max_Priority_Proposal[round] = None

					if not self.Max_Priority_Proposal[round]:

						self.Max_Priority_Proposal[round]=priority
						
					else:
						if priority>=self.Max_Priority_Proposal[round]:
							self.Max_Priority_Proposal[round]=priority
						else:
							continue

				else:

					continue


			elif mes_type=='v':


				key = msg[1]
				msg_id = msg[0]+str(key[0])+str(key[1])+msg[2].decode('utf-8')+str(msg[4])

				if msg_id not in self.Gossiped_Msg:
					self.Gossiped_Msg.append(msg_id)
					#self.Gossip_Msg(msg)
					delay = inpipe.delay


					if delay>1:

						timer = 0
						step = 5
						while timer<delay:
							timer+=step
							yield self.env.timeout(step)

					vote_info = (msg[2], msg[3], msg[4])

					self.Vote_Msg.setdefault(key, []).append(vote_info)

				else:

					continue
			else:
				continue


	def CountVotes(self,ctx, round, step, committe_size= None, step_thresh=None,timeout_lambda=2):

		ba_thresh = 2/3
		if step == Final_State:
			ba_thresh = 0.74

		try:

			key = (round, step)

			if step==Final_State:
				thresh_vote = ba_thresh * 10000
			else:
				thresh_vote = ba_thresh*self.manual_committee_size
			
			if self.Vote_Msg[key]:
				
				nums = len(self.Vote_Msg[key])
				for n in range(0,nums):
					msg = self.Vote_Msg[key].pop()
					voter = msg[0]
					block_hash=msg[1]
					votes=msg[2]
			
					if self.store_voters(round,step,votes,voter):
						self.store_vote(round,step,block_hash,votes)
						if self.vote_buffer[key][block_hash]>thresh_vote:
							return block_hash
				return False
			else:
				
				for block_hash in self.vote_buffer[key]:
					if self.vote_buffer[key][block_hash]>thresh_vote:
						return block_hash
					
				return False

		except KeyError as e:
			#print(f'node {self.id} doesnot recived any votes msg at time {self.env.now} with error {e}')
			return False

	def BA(self, ctx, current_round, block_hash,delays):

		h_block = yield self.env.process(self.Reduction(ctx, current_round, block_hash,delays))



		#print(f'node {self.id} gossiped mes {len(self.Gossiped_Msg)}')


		h_block_from_bba = yield self.env.process(self.Binary_BA(ctx,current_round,h_block))


		final_step_committee = self.manual_committee_size

		yield self.env.timeout(10)
		max_step = 20000
		step = 0
		while not self.CountVotes(ctx, current_round, step=Final_State):
			if step < max_step:
				step += 10
				yield self.env.timeout(10)


			else:
				break
		
		r = self.CountVotes(ctx, current_round,Final_State, final_step_committee)
		key=(current_round,Final_State)
		if key in self.vote_buffer.keys():
			print(f'final vote result {self.vote_buffer[key]}')
		print(f'node {self.id} final count result {r}')
		#print(f'node {self.id} result from bba {h_block_from_bba}')
		if h_block_from_bba==r:
			return (Final_State, h_block_from_bba)
		else:
			return (Tenative_State, h_block_from_bba)


	def Reduction(self, ctx, current_round, block_hash,delays):
		empty_block = self.generate_empty_block(current_round)
		#step 1

		#print('enter reduction')
		reduction_step_one = 'reduction1'

		#threshnum = self.manual_committee_size
		self.Committe_vote(ctx, current_round, reduction_step_one, self.manual_committee_size, block_hash)
		yield self.env.timeout(10)
		### simulation waiting
		max_step = 20000+delays
		step = 0

		while not self.CountVotes(ctx, current_round, reduction_step_one):
			if step < max_step:
				step += 10
				yield self.env.timeout(10)
			else:
				break
		
		###end of waiting code
		#set for committe_size whilte testing

		#step_one_result = self.CountVotes(ctx, current_round, step=reduction_step_one, committe_size=self.manual_committee_size)
		step_one_result = self.CountVotes(ctx, current_round, reduction_step_one)
		print(f'with result {step_one_result}, node {self.id} finished recution1 count at time {self.env.now} ms')
		print(f'node {self.id} vote buffer {self.vote_buffer}')

		if self.id == 1:
			print(f'{self.vote_buffer}')
		
		#start of reduction 2

		max_step = 20000
		reduction_step_two='reduction2'


		if not step_one_result:
			#commitee vote for empty block

			print(f'node {self.id} reduction2 start with empty')
			self.Committe_vote(ctx, current_round, reduction_step_two, self.manual_committee_size, empty_block.block_hash)

		else:

			print(f'node {self.id} reduction with none empty')
			self.Committe_vote(ctx, current_round, reduction_step_two, self.manual_committee_size, step_one_result)

		yield self.env.timeout(10)

		step = 0
		while not self.CountVotes(ctx, current_round, step=reduction_step_two):
			if step < max_step:
				step += 10
				yield self.env.timeout(10)


			else:
				break

		#step_two_result = self.CountVotes(ctx,current_round, step=reduction_step_two,committe_size= self.manual_committee_size)
		step_two_result = self.CountVotes(ctx, current_round, step=reduction_step_two,
		                                  committe_size=self.manual_committee_size)
		print(f'reduction 2 result {step_two_result}')
		if not step_two_result:

			return empty_block.block_hash
		else:

			return step_two_result




	def Binary_BA(self, ctx, round, block_hash):
		max_step = 20

		step=1

		r = block_hash
		manual_threshold = self.manual_committee_size

		empty_block = self.generate_empty_block(round)
		max_s = 20000

		while step <= max_step:
			step_prefix = 'bba'
			#yield self.env.process(self.Committe_vote(ctx, round, step_prefix+str(step), manual_threshold, r))
			self.Committe_vote(ctx, round, step_prefix + str(step), manual_threshold, r)
			yield self.env.timeout(10)
			### simulation waiting
			s=0
			while not self.CountVotes(ctx, round, step_prefix + str(step)):
				if s < max_s:
					s += 100
					yield self.env.timeout(100)


				else:

					break
			###end of waiting code
			r = self.CountVotes(ctx, round, step_prefix + str(step), manual_threshold)

			#print(f'node {self.id} check if block hash is equal to empty {r == empty_block.block_hash}')
			if not r:
				r = block_hash

			elif r != empty_block.block_hash:

				for step_prime in range(step+1,step+4):

					#yield self.env.process(self.Committe_vote(ctx,round,step_prefix+str(step_prime), manual_threshold,r))
					self.Committe_vote(ctx, round, step_prefix + str(step_prime), manual_threshold, r)

				if step == 1:
					print(f'node {self.id} calling final at bba1 with hash {r}')
					#yield self.env.process(self.Committe_vote(ctx, round, Final_State, manual_threshold, r))
					self.Committe_vote(ctx, round, Final_State, manual_threshold, r)

				return r

			step+=1
			print(f'node {self.id} entering step2 in bba')

			self.Committe_vote(ctx, round, step_prefix + str(step), manual_threshold, r)


			yield self.env.timeout(10)

			### simulation waiting
			s=0
			while not self.CountVotes(ctx, round, step_prefix + str(step)):
				if s < max_s:
					s += 10
					yield self.env.timeout(10)


				else:

					break
			###end of waiting code

			#r = self.CountVotes(ctx,round,step_prefix+str(step),manual_threshold)
			r = self.CountVotes(ctx, round, step_prefix + str(step), manual_threshold)

			if not r:
				r = empty_block.block_hash
			elif r == empty_block.block_hash:
				for step_prime in range(step+1,step+4):
					#yield self.env.process(self.Committe_vote(ctx,round, step_prefix+str(step_prime),manual_threshold,r))
					self.Committe_vote(ctx, round, step_prefix + str(step_prime), manual_threshold, r)
				self.Committe_vote(ctx,round,Final_State, manual_threshold, r)
				return r

			step+=1

			#yield self.env.process(self.Committe_vote(ctx, round,step_prefix+str(step),manual_threshold,r))
			self.Committe_vote(ctx, round, step_prefix + str(step), manual_threshold, r)
			yield self.env.timeout(10)
			#r = self.CountVotes(ctx,round,step_prefix+str(step),self.manual_committee_size)
			### simulation waiting
			s=0
			while not self.CountVotes(ctx, round, step_prefix + str(step)):
				if s < max_step:
					s += 10
					yield self.env.timeout(10)


				else:

					break
			###end of waiting code
			r = self.CountVotes(ctx, round, step_prefix + str(step), self.manual_committee_size)

			if not r:

				if self.CommonCoin(ctx, round, step_prefix+str(step),manual_threshold) == 0:

					r = block_hash
				else:
					r = empty_block.block_hash

			step+=1

		return r
	#store vote buffer
	def store_vote(self, round, step, block_hash, votes):

		key = (round,step)

		if key in self.vote_buffer.keys():

			if block_hash in self.vote_buffer[key].keys():
				self.vote_buffer[key][block_hash]+=votes
			else:
				self.vote_buffer[key][block_hash]=votes

		else:

			self.vote_buffer[key]=dict()
			self.vote_buffer[key][block_hash]=votes
		#self.vote_buffer.setdefault(key,[]).append(votes)

	def clean_vote_buffer(self,round):
		keys_to_del=[]
		for k in self.vote_buffer.keys():
			if k[0]==round:
				keys_to_del.append(k)
		for key in keys_to_del:
			del self.vote_buffer[key]
	
	def clean_block(self,round):
		del self.block_candidates[round]
		del self.Max_Priority_Proposal[round]
	
	def clean(self,round):
		self.clean_vote_buffer(round)
		self.clean_block(round)
		
	def store_voters(self,round,step, votes, voter):

		key = (round,step)
		self.voters.setdefault(key,set()).add(voter)
		
		return True
		
	def Committe_vote(self, ctx, round, step, threshold, value):

		seed, user_tokens, prev_blockhash= ctx

		role = committe_member+str(round)+str(step)
		if step==Final_State:
		 	threshold=10000
		sort_result = self.Sortition(self.sk, round, role, threshold)
	
		if sort_result:
			#value is the incoming candidate blockhash
			#print(f'at time {self.env.now} node {self.id} selected as committe with token {self.tokens} in step {step} and round {round} with votes {sort_result[2]}')

			selfvotes = sort_result[2]
			vote_message = ('v', (round,step),self.pk, value, selfvotes)

			#new_vote = ('v', (round, step), self.pk, value, selfvotes, self.city)
			#vote_message=(self.env.now, self.pk,vote_message,self.id)

			self.store_voters(round, step,selfvotes, self.pk)
			self.store_vote(round, step, value, selfvotes)

			msg_id = str(round) + str(step) + self.pk.decode('utf-8')+str(selfvotes)
			self.Gossip_Msg(vote_message)
			self.Gossiped_Msg.append(msg_id)
		else:
			self.Vote_Msg[(round,step)]=[]




	def propose_block(self,sortition_result, current_round):

		proof,hash,j,indexes = sortition_result

		#getting seed
		hashstring_for_seed = self.get_seed(current_round) + str(current_round)
		proof_for_seed = vrftool.get_proof(self.sk, hashstring_for_seed)
		new_seed = vrftool.get_hash(proof_for_seed)

		new_block = Block(current_round, self.chain.chain[current_round - 1].block_hash,
		                  self.pk, proof, new_seed)
		new_block.gen_bhash()

		# caculate the max priority among all subusers
		priority, max_index = self.max_priority(new_block.block_hash, indexes)
		new_block.add_priority(priority)
		# self is proposer then add hihest proority block into self block block_candidates

		self.block_candidates[current_round]=[new_block]
		filename=f'{str(current_round)}blockproposals.txt'
		file_path = 'RoundStatus/' + filename
		dirpath='/scratch/yliu7/'
		folder_path = os.path.join(dirpath, file_path)
		with open(folder_path,'a+') as f:
			f.write(f'{new_block.block_hash}\n')


		proposal_msg = ('b', current_round, new_block)
		priority_msg = ('p',current_round, new_block.block_hash,priority)
		self.Max_Priority_Proposal[current_round]=priority
		msg_id = 'b' + str(current_round) + new_block.block_hash + priority
		pmsg_id = 'p' + str(current_round) + new_block.block_hash + priority
		self.Gossiped_Msg.append(msg_id)
		self.Gossiped_Msg.append(pmsg_id)
		self.Gossip_Msg(priority_msg)
		self.Gossip_Msg(proposal_msg)

		print(f'node {self.id} sent out proposal msg with block hash {new_block.block_hash} with priority {priority}for its peer at time{self.env.now}')

	def handle_result(self,current_round, block_hash):
		empty_block=self.generate_empty_block(current_round)

		if block_hash == empty_block.block_hash:
			new_block = empty_block
			self.chain.chain[current_round] = new_block

			print(f'node {self.id} reaches final consensus at time {self.env.now} with empty block ')
			return True
		else:

			new_block = None
			for candidate in self.block_candidates[current_round]:
				if candidate.block_hash == block_hash:
					new_block = candidate
			if new_block:
				self.chain.chain[current_round] = new_block
				print(
					f'node {self.id} reaches final consensus at time {self.env.now} with blockhash{new_block.block_hash} ')
				return True
			else:

				return False
	#common coin
	def CommonCoin(self, ctx, round, step, thresh_num):
		minhash = 'f'*64

		#print('timeout for msg to coming in ')
		yield self.env.timeout(100)
		try:
			if self.Vote_Msg[(round,step)]:

				for msg in self.Vote_Msg[(round,step)]:

						js = msg.votes
						sort_hash = msg.voteinfo[1]
						for j in range(0,js):

							hash_string = sort_hash.decode('utf-8')+str(j)
							new_hash = sha256(hash_string.encode('utf-8')).digest().hex()

							if new_hash<minhash:
								minhash = new_hash

			minhash = int(minhash,16)
			return minhash % 2
		except KeyError as e:


			return 0
		#print('comming coin minhash result ', minhash%2)


	#crypto sortition
	# if there is selected subuser, return number of subusers and indexes
	# if sortition is null, return False
	def Sortition(self,secret_key, round, role, thresh_num):


		vrfstring = self.get_seed(round) + role

		proof = vrftool.get_proof(secret_key, vrfstring)

		hash = vrftool.get_hash(proof)

		# probs shoud be equal to the threshhold set by the system
		# proposers/totla_tokens, varing from 26 to 70
		probs = thresh_num / self.chain.total_tokens

		#get the subuser number and indexes
		js, indexes = self.sub_users(self.tokens, probs, hash)
		dirpath='/scratch/yliu7/'
		filename = f'Round{str(round)}sort.txt'
		file_path = 'SortRes/' + filename
		path = os.path.join(dirpath, file_path)
		
		if js==0:
			
			return False
		else:
			result =(proof,hash,js,indexes)
			with open(path,"a+") as f:
				f.write(f'{self.id},{round},{role},{js} \n')
			return result
		# if role == block_proposer:elif role == committe_member:

	#get context info using current round_number
	# return seed, user_total_tokens, previous block in the chain

	def get_ctx(self,current_round):

		return (self.get_seed(current_round), self.tokens, self.chain.chain[current_round-1].block_hash)


	#current ongoing round shoud be chain rounds+1
	#chain stores valid
	def get_current_round(self):
		return self.chain.rounds+1

	def find_max_priority_proposal(self,current_round):
		index = 0
		count = 0
		highest_priority = 0
		for block in self.block_candidates[current_round]:
			if count == 0:
				index = 0
				highest_priority = block.priority

			else:
				if block.priority > highest_priority:
					index = self.block_candidates[current_round].index(block)
					highest_priority = block.priority
			count += 1
		return index

	def Verify_Sort(self, pk, hash, proof, seed, thresh_num, role, user_total_tokens):

		#to be implemented

		return vrftool.verify_proof(proof,pk, (seed+role))


	def generate_empty_block(self,current_round):
		null_priority = hex(0)
		hashstring_for_seed = self.get_seed(current_round) + str(current_round)
		proof_for_seed = vrftool.get_proof(system_sk, hashstring_for_seed)
		new_seed = vrftool.get_hash(proof_for_seed)
		empty_block = Block(current_round, self.chain.chain[current_round-1].block_hash, author=system_pk,author_proof=proof_for_seed, seed = new_seed, isEmpty=True)

		empty_block.add_priority(null_priority)

		return empty_block

	def Verify_Gossip(self, message, ctx=None):
		pk = message.pk
		proof = message.proof
		round = message.round

		if message.isProposal:
			if round - len(self.chain.chain)>1:
				print(f'node {self.id} cant verify coz outdated chain')
				return False
			seed =self.get_seed(round)
			hashstring = seed + block_proposer

			return vrftool.verify_proof(proof,pk, hashstring)

		else:
			if not ctx:
				return False
			else:
				vote_vrfstring = committe_member+str(message.round)+str(message.voteinfo[0])
				return vrftool.verify_proof(proof, pk, vote_vrfstring)


	def check_proposal(self,round):
		max_p = self.Max_Priority_Proposal[round]
		for block in self.block_candidates[round]:
			if block.priority == max_p:
				return True
		return False

	def get_seed(self,current_round):

		seed = self.chain.chain[current_round-1].seed
		if current_round>1:
			seed = seed.decode('utf-8')

		return seed

	#generating new seed when proposing block, where j is the subuser index;
	def new_seed(self,current_round):
		#format round from int to bytes
		newround = str(current_round).encode('utf-8')
		seed = self.get_seed(1).encode('utf-8')
		return seed+newround

	#get number and index of qualified subusers
	#return how many subusers along with their indexes
	def sub_users(self,user_total_tokens,probs,hash):
		indexes_of_j = []
		hash = hash.decode('utf-8')
		val = bin(int(hash, 16))

		total = pow(2, 512)
		num = int(val, 2)
		hashprob = num / total

		j = 0
		
		
		flag = False

		while j < user_total_tokens:
			lower = get_bond(j, user_total_tokens, probs)
			upper = get_bond(j + 1, user_total_tokens, probs)
			if j == 0 and hashprob < lower:
				return j, indexes_of_j
			if lower <= hashprob and hashprob < upper:
				j += 1
				indexes_of_j.append(j)
				flag = True
				break
			elif hashprob < lower or hashprob >= upper:
				indexes_of_j.append(j)
				j += 1
		if not flag:
			j = 0
			indexes_of_j = []
			return j, indexes_of_j
		return j, indexes_of_j

	def fetch_proposal(self,round,ba_result):
		for block in self.block_candidates[round]:
			if block.block_hash == ba_result:
				return block
		return False
		
	def clean_buffers(self):
		self.block_candidates.clear()
		self.Gossiped_Msg.clear()
		self.vote_buffer.clear()
		self.Vote_Msg.clear()

	#  sort the max priority subuser of user
	def max_priority(self, block_hash, subuser_indexes):
		max_p = hex(0)
		max_subindex = 0
		for x in subuser_indexes:
			hashstring = block_hash.encode('utf-8')+str(x).encode('utf-8')
			hash_res = sha256(hashstring).digest().hex()

			if hash_res>max_p:
				max_p=hash_res
				max_subindex=x
		return max_p, max_subindex

	#sotre block and author
	def store_blockHash_to_proof(self,hash, proof):

		if hash not in self.blocks_and_proof.keys():
			self.blocks_and_proof[hash] = proof
