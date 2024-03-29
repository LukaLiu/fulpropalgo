import random


import pysnooper
import simpy
RANDOM_SEED = 42
SIM_TIME = 100


class BroadcastPipe(object):
    """A Broadcast pipe that allows one process to send messages to many.

    This construct is useful when message consumers are running at
    different rates than message generators and provides an event
    buffering to the consuming processes.

    The parameters are used to create a new
    :class:`~simpy.resources.store.Store` instance each time
    :meth:`get_output_conn()` is called.

    """
    def __init__(self, env, capacity=simpy.core.Infinity):
        self.env = env
        self.capacity = capacity
        self.pipes = []

    def put(self, value):
        """Broadcast a *value* to all receivers."""
        if not self.pipes:
            raise RuntimeError('There are no output pipes.')

        events = [store.put(value) for store in self.pipes]
        return self.env.all_of(events)  # Condition event for all "events"

    def get_output_conn(self):
        """Get a new output connection for this broadcast pipe.

        The return value is a :class:`~simpy.resources.store.Store`.

        """


        pipe = simpy.Store(self.env, capacity=self.capacity)
        self.pipes.append(pipe)
        print(f'in broadcast getoutput con testing pipes {self.pipes}')
        return pipe


def message_generator(name, env, out_pipe):
    """A process which randomly generates messages."""
    while True:
        # wait for next transmission
        yield env.timeout(random.randint(6, 10))

        # messages are time stamped to later check if the consumer was
        # late getting them.  Note, using event.triggered to do this may
        # result in failure due to FIFO nature of simulation yields.
        # (i.e. if at the same env.now, message_generator puts a message
        # in the pipe first and then message_consumer gets from pipe,
        # the event.triggered will be True in the other order it will be
        # False
        msg = (env.now, '%s says hello at %d' % (name, env.now))
        print(f'at time {env.now} {name} says hello ')
        out_pipe.put(msg)


def message_consumer(name, env, in_pipe):
    """A process which consumes messages."""
    while True:
        # Get event for message pipe
        msg = yield in_pipe.get()
        print(f'{name} recived msg {msg} at time {env.now}')
        if msg[0] < env.now:
            # if message was already put into pipe, then
            # message_consumer was late getting to it. Depending on what
            # is being modeled this, may, or may not have some
            # significance
            print('LATE Getting Message: at time %d: %s received message: %s' %
                  (env.now, name, msg[1]))

        else:
            # message_consumer is synchronized with message_generator
            print('at time %d: %s received message: %s.' %
                  (env.now, name, msg[1]))



        # Process does some other work, which may result in missing messages
        yield env.timeout(random.randint(4, 8))


# Setup and start the simulation
print('Process communication')


# For one-to many use BroadcastPipe
# (Note: could also be used for one-to-one,many-to-one or many-to-many)

def simu():
    env = simpy.Environment()

    bc_pipe = BroadcastPipe(env)

    env.process(message_generator('Generator A', env, bc_pipe))
    print(bc_pipe.pipes)
    env.process(message_consumer('Consumer A', env, bc_pipe.get_output_conn()))
    print(bc_pipe.pipes)
    env.process(message_consumer('Consumer B', env, bc_pipe.get_output_conn()))

    print('\nOne-to-many pipe communication\n')
    env.run(until=30)
    print(f'after finsihing thee pipes {bc_pipe.pipes}')
simu()