import gym
from gym import spaces
import numpy as np
import heapq
import collections
from os import path
from os import sys
import math
import random

try:
    import Queue as Q  # ver. < 3.0
except ImportError:
    import queue as Q

events = 0


# /* Event structure. */
# 分别是：
# 目的节点
# 源节点
# 当前节点
# 包的创建时间
# 跳数
# When create.
# When remove or insert.
class event:
    def __init__(self, time, dest):
        # /* Initialize new event. */
        self.dest = dest
        self.source = UNKNOWN
        self.node = UNKNOWN
        self.birth = time
        self.hops = 0
        self.etime = time # 应该这样理解，处理它的时间，就是remove它的时间。这个时间是随着进行，慢慢变大的。确定！！！搞定
        self.qtime = time


# /* Special events. */
INJECT = -1
REPORT = -2
END_SIM = -3
UNKNOWN = -4

# /* Define. */
# 空event list

NIL = Nil = -1


class NetworkSimulatorEnv(gym.Env):

    # We init the network simulator here
    def __init__(self):
        self.viewer = None
        self.graphname = 'data/lata.net'
        self.done = False
        self.success_count = 0
        self.nnodes = 0
        self.nedges = 0
        self.enqueued = {} # Time of last in line.
        self.nenqueued = {} # How many in queue?
        self.interqueuen = [] #Initialized to interqueue.
        self.event_queue = []  # Q.PriorityQueue()
        self.nlinks = {}
        self.links = collections.defaultdict(dict)
        self.total_routing_time = 0.0
        self.routed_packets = 0
        self.total_hops = 0
        self.current_event = event(0.0, 0)  # do I need to do this?
        self.internode = 1.0  # Time in transit.
        self.interqueue = 1.0  # Time between handlings. (init)
        self.active_packets = 0
        self.queuelimit = 100
        self.send_fail = 0
        self.callmean = 1  # network load

        self.distance = []  # np.zeros((self.nnodes,self.nnodes))
        self.shortest = []  # np.zeros((self.nnodes,self.nnodes))

        self.next_dest = 0
        self.next_source = 0
        self.injections = 0 # 注入包的数量
        self.queue_full = 0

        self.events = 0

        self.sources = [52, 63, 21, 9, 96, 1, 89, 0, 102, 67, 21, 48, 110, 16, 68, 112, 88, 24, 6, 64, 28, 25, 0, 72,
                        63, 45, 18, 23, 33, 86, 30, 25, 56, 35, 81, 107, 0, 56, 71, 3, 46, 47, 24, 53, 20, 95, 53, 67,
                        58, 60, 28, 99, 14, 16, 28, 25, 7, 65, 100, 52, 4, 100, 13, 42, 59, 15, 35, 77, 89, 63, 35, 42,
                        56, 69, 61, 74, 73, 24, 58, 7, 0, 113, 5, 14, 37, 103, 63, 10, 69, 59, 63, 55, 25, 77, 65, 34,
                        0, 41, 9, 46, 18, 54, 35, 75, 41, 105, 8, 113, 32, 108, 55, 19, 64, 19, 19, 95, 47, 40, 114, 14,
                        17, 10, 51]
        self.dests = [77, 21, 65, 35, 80, 59, 78, 72, 112, 2, 80, 101, 2, 57, 0, 13, 42, 72, 19, 56, 66, 22, 50, 80, 16,
                      24, 89, 110, 65, 113, 71, 87, 68, 52, 87, 112, 8, 95, 74, 79, 18, 50, 83, 101, 38, 31, 114, 109,
                      100, 58, 38, 53, 83, 11, 67, 57, 83, 49, 36, 80, 79, 60, 30, 102, 86, 69, 91, 37, 109, 28, 56, 65,
                      55, 42, 58, 4, 83, 16, 98, 96, 14, 66, 73, 97, 28, 40, 43, 28, 90, 40, 49, 74, 21, 59, 77, 34, 82,
                      103, 39, 23, 2, 36, 93, 68, 85, 88, 90, 115, 35, 27, 43, 103, 71, 3, 35, 6, 97, 7, 54, 10, 93, 35,
                      66]

        self.next_source = 0
        self.next_dest = 0

    def _step(self, action):
        # if(self.total_routing_time/self.routed_packets < 10): #totally random, need change

        current_event = self.current_event
        # etime呢？？？ 这个event在被处理时的时间，也就是remove的时间
        current_time = current_event.etime
        current_node = current_event.node

        # node A --> node B: 当前时间（已经在B了）-路上的transit时间internode - 之前入队（A）的时间，就是在队列（A）中等待排队的时间
        # current_time.etime是挪到B之后的时间，current_time.qtime是上次被挪的时间，
        time_in_queue = current_time - current_event.qtime - self.internode

        # if the link wasnt good
        # link是个dict，key=node, value 是对应的action
        if action < 0 or action not in self.links[current_node]:
            next_node = current_node

        else:
            next_node = self.links[current_node][action]
        # handle the case where next_node is your destination
        if next_node == current_event.dest:
            # reward = 排队的时间 + 节点间transit的时间
            reward = time_in_queue + self.internode  # possibly change? totally random currently

            self.routed_packets += 1
            self.nenqueued[current_node] -= 1
            self.total_routing_time += current_time - current_event.birth + self.internode
            self.total_hops += current_event.hops + 1

            self.active_packets -= 1

            # 这个 packet 到了目的地以后，重新产生一个新 packet，get_new_packet_bump()
            self.current_event = self.get_new_packet_bump()

            if self.current_event == NIL:
                return ((current_event.node, current_event.dest),
                        (current_event.node, current_event.dest)), reward, self.done, {}
            else:
                # 当前处理过的（刚处理好），当前新指向的event
                return ((current_event.node, current_event.dest),
                        (self.current_event.node, self.current_event.dest)), reward, self.done, {}

        else:
            # #if the queue is full at the next node, set destination to self
            # 队列满了，就失败了
            if self.nenqueued[next_node] >= self.queuelimit:
                self.send_fail = self.send_fail + 1
                next_node = current_node

            reward = time_in_queue + self.internode

            # do send. 把当前状态指向采取action后的节点上
            current_event.node = next_node  # do the send!
            current_event.hops += 1
            # 这里考虑的是next_node的对列里如果刚进来包，那么你进来的时间就是队列里最新进来的时间+传输时间，否则就是current——time + 传输时间了
            next_time = max(self.enqueued[next_node] + self.interqueuen[next_node],
                            current_time + self.internode)  # change this to nexttime = Max(enqueued[n_to]+interqueuen[n_to], curtime+internode); eventually
            # 这里更新时间了，哈哈哈，
            # 不要纠结next_time, 反正next_time 就指向了current_time了。
            current_event.etime = next_time
            # enqueue[node] 是 node上队列里packet最新入队的时间
            self.enqueued[next_node] = next_time
            # 这个event被开始处理，说明这个event已经被执行了action，现在只是更新这个event的信息！！！那么current_time 就是这个event的包插到"next_node"（当前已经在next_node上了） 的时间
            # 就是event被insert的时间，就是开始处理这个event的时间（应该是忽略了插入操作需要的时间，认为是0）
            current_event.qtime = current_time
            if type(current_event) == int:
                print("this is current_event:{}".format(current_event))
            heapq.heappush(self.event_queue, ((current_time + 1.0, -self.events), current_event))
            self.events += 1

            # 这里应该是更新下队列状态
            self.nenqueued[next_node] += 1
            self.nenqueued[current_node] -= 1

            # ??? 这里没有到终点，为什么重新发射一个包(不是的，上面刚把current_event塞进队列里，这里发射包的函数里，只是要把它弹出来，除非current_event的状态是current_event.source == INJECT，才会start new packet)
            # 这里是重新开始处理一个event，刚才那个event已经处理完毕并放在了 heapq 内
            self.current_event = self.get_new_packet_bump()

            # return state_pair 是个tuple，第一个放的是，state执行action后转移到的state， 第二个放的是当前待处理的event（event对列中，队顶的）。所以这俩可能是一个event，也可能不是
            if self.current_event == NIL:
                return ((current_event.node, current_event.dest),
                        (current_event.node, current_event.dest)), reward, self.done, {}
            else:
                return ((current_event.node, current_event.dest),
                        (self.current_event.node, self.current_event.dest)), reward, self.done, {}

    def _reset(self):
        self.readin_graph()
        self.distance = np.zeros((self.nnodes, self.nnodes))
        self.shortest = np.zeros((self.nnodes, self.nnodes))
        self.compute_best()
        self.done = False
        # 每个node都初始化queue 为 1
        self.interqueuen = [self.interqueue] * self.nnodes

        self.event_queue = []  # Q.PriorityQueue()
        self.total_routing_time = 0.0

        self.enqueued = [0.0] * self.nnodes
        self.nenqueued = [0] * self.nnodes

        inject_event = event(0.0, 0)
        inject_event.source = INJECT
        # call mean 应该就是负载的意思 network load
        if self.callmean == 1.0:
            inject_event.etime = -math.log(random.random())
        else:
            inject_event.etime = -math.log(1 - random.random()) * float(self.callmean)

        self.events = 1

        inject_event.qtime = 0.0
        heapq.heappush(self.event_queue, ((1.0, -self.events), inject_event))
        self.injections += 1
        self.events += 1

        self.current_event = self.get_new_packet_bump()

        return ((self.current_event.node, self.current_event.dest), (self.current_event.node, self.current_event.dest))

    ###########helper functions############################
    # Initializes a packet from a random source to a random destination

    # 构建graph：
    # nlinks是 {} , 里面是每个node的连接 {"1":[2,3,4], "2":[3,5], ... }
    def readin_graph(self):
        self.nnodes = 0
        self.nedges = 0
        graph_file = open(self.graphname, "r")

        for line in graph_file:
            line_contents = line.split()

            if line_contents[0] == '1000':  # node declaration

                self.nlinks[self.nnodes] = 0
                self.nnodes = self.nnodes + 1

            if line_contents[0] == '2000':  # link declaration

                node1 = int(line_contents[1])
                node2 = int(line_contents[2])

                self.links[node1][self.nlinks[node1]] = node2
                self.nlinks[node1] = self.nlinks[node1] + 1

                self.links[node2][self.nlinks[node2]] = node1
                self.nlinks[node2] = self.nlinks[node2] + 1

                self.nedges = self.nedges + 1

    # 创建一个 packet ，指定source 和 dest ，并且把它放入 source 的 queue 里
    def start_packet(self, time):
        source = np.random.random_integers(0, self.nnodes - 1)
        dest = np.random.random_integers(0, self.nnodes - 1)

        # make sure we're not sending it to our source
        while source == dest:
            dest = np.random.random_integers(0, self.nnodes - 1)

        # is the queue full? if so don't inject the packet
        if self.nenqueued[source] > self.queuelimit - 1:
            self.queue_full += 1
            return (Nil)

        # source node 的队列里，包的数量+1
        self.nenqueued[source] = self.nenqueued[source] + 1

        # 总的激活的 packet 数量+1
        self.active_packets = self.active_packets + 1
        #初始化这个包，源地址，目的地址，当前节点点指好。
        current_event = event(time, dest)
        current_event.source = current_event.node = source

        return current_event

    # 发射一个packet？从heapq里取出顶上的event，然后 Lets a node process one packet. 其实是处理队顶上的event，这个event如果是刚注入，那么初始化他，否则，返回这个event
    def get_new_packet_bump(self):

        current_event = heapq.heappop(self.event_queue)[1]
        #current_time 是 这个event入队的时间
        current_time = current_event.etime

        # make sure the event we're sending the state of back is not an injection
        while current_event.source == INJECT:
            # 这里是模拟产生packet的时间，或者是加一个间隔
            if self.callmean == 1.0 or self.callmean == 0.0:
                current_event.etime += -math.log(1 - random.random())
            else:
                current_event.etime += -math.log(1 - random.random()) * float(self.callmean)

            current_event.qtime = current_time

            heapq.heappush(self.event_queue, ((current_time + 1.0, -self.events), current_event))
            self.events += 1
            current_event = self.start_packet(current_time)
            if current_event == NIL:
                current_event = heapq.heappop(self.event_queue)[1]

        if current_event == NIL:
            current_event = heapq.heappop(self.event_queue)[1]
        return current_event

    # Pretend to send node's packet over given link.
    def pseudostep(self, action):

        current_event = self.current_event
        current_time = self.current_event.etime
        current_node = self.current_event.node
        # 当前时间-入队时间-transit(中转)时间
        time_in_queue = current_time - current_event.qtime - self.internode
        # reward = 队列的排队时间 + 中转时间
        reward = time_in_queue + self.internode

        # 没有这个连接
        # if the link wasnt good
        if action < 0 or action not in self.links[current_node]:
            return reward, (current_node, current_event.dest)

        else:
            next_node = self.links[current_node][action]
            if next_node != current_event.dest:
                next_time = max(self.enqueued[next_node] + self.interqueuen[next_node],
                                current_time + self.internode)  # change this to nexttime = Max(enqueued[n_to]+interqueuen[n_to], curtime+internode); eventually

            return reward, (next_node, current_event.dest)

    def compute_best(self):

        changing = True

        for i in range(self.nnodes):
            for j in range(self.nnodes):
                if i == j:
                    self.distance[i][j] = 0
                else:
                    self.distance[i][j] = self.nnodes + 1
                self.shortest[i][j] = -1

        while changing:
            changing = False
            for i in range(self.nnodes):
                for j in range(self.nnodes):
                    # /* Update our estimate of distance for sending from i to j. */
                    if i != j:
                        for k in range(self.nlinks[i]):
                            # 如果i,j的距离 > i 的邻居点，j的距离 + 1，说明距离还没稳定，继续调整
                            # shortest[i][j] 其实是i到j的最短路径的下一跳的link，走哪个link
                            if self.distance[i][j] > 1 + self.distance[self.links[i][k]][j]:
                                self.distance[i][j] = 1 + self.distance[self.links[i][k]][j]  # /* Better. */
                                self.shortest[i][j] = k
                                changing = True
