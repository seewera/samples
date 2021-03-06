#!/usr/bin/env python
'''
Author: Shih-Yuan Liu
'''

import rospy
import copy
from duckietown_msgs.msg import FSMState, BoolStamped
from duckietown_msgs.srv import SetFSMState, SetFSMStateRequest, SetFSMStateResponse

class FSMNode(object):
    def __init__(self):
        self.node_name = rospy.get_name()

        # Load transition dictionray
        self.states_dict = rospy.get_param("~states")

        # Validate state transitions
        if not self.validateStates(self.states_dict):
            # Print error message and shutdown incoherent
            rospy.signal_shutdown("[%s] Incoherent definition." %self.node_name)
            return          

        # Setup initial state
        self.state_msg = FSMState()
        self.state_msg.state = rospy.get_param("~initial_state")
        self.state_msg.header.stamp = rospy.Time.now()
        # Setup publisher and publish initial state
        self.pub_state = rospy.Publisher("~mode",FSMState,queue_size=1,latch=True)
    
        # Provide service
        self.srv_state = rospy.Service("~set_state",SetFSMState,self.cbSrvSetState)

        # Construct publishers
        self.pub_dict = dict()
        nodes = rospy.get_param("~nodes")

        self.active_nodes = None
        for node_name, topic_name in nodes.items():
            self.pub_dict[node_name] = rospy.Publisher(topic_name, BoolStamped, queue_size=1, latch=True)

        # Construct subscribers
        param_events_dict = rospy.get_param("~events")
        self.sub_list = list()
        for event_name, topic_name in param_events_dict.items():
            self.sub_list.append(rospy.Subscriber("%s"%(topic_name), BoolStamped, self.cbEvent, callback_args=event_name))

        rospy.loginfo("[%s] Initialized." %self.node_name)
        # Publish initial state
        self.publish()

    def validateStates(self,states_dict):
        valid_states = states_dict.keys()
        for state, state_dict in states_dict.items():        
            # Validate the existence of all reachable states
            transitions_dict = state_dict.get("transitions")
            if transitions_dict is None:
                continue
            else:
                for transition, next_state in transitions_dict.items():
                    if next_state not in valid_states:
                        rospy.logerr("[%s] %s not a valide state. (From %s with event %s)" %(self.node_name,next_state,state,transition))
                        return False
        return True

    def _getNextState(self, state_name, event_name):
        state_dict = self.states_dict.get(state_name)
        if state_dict is None:
            rospy.logwarn("[%s] %s not defined. Treat as terminal. "%(self.node_name,state_name))
            return None
        else:
            if "transitions" in state_dict:
                next_state = state_dict["transitions"].get(event_name)
            else:
                next_state = None
            return next_state
                
    def _getActiveNodesOfState(self,state_name):
        state_dict = self.states_dict[state_name]
        active_nodes = state_dict.get("active_nodes")
        if active_nodes is None:
            rospy.logwarn("[%s] No active nodes defined for %s. Deactive all nodes."%(self.node_name,state_name))
            active_nodes = []
        return active_nodes

    def publish(self):
        self.publishBools()
        self.publishState()

    def cbSrvSetState(self,req):
        self.state_msg.header.stamp = rospy.Time.now()
        self.state_msg.state = req.state
        self.publish()
        return SetFSMStateResponse()

    def publishState(self):
        self.pub_state.publish(self.state_msg)
        rospy.loginfo("[%s] FSMState: %s" %(self.node_name, self.state_msg.state))

    def publishBools(self):
        msg = BoolStamped()
        msg.header.stamp = self.state_msg.header.stamp
        active_nodes = self._getActiveNodesOfState(self.state_msg.state)
        for node_name, node_pub in self.pub_dict.items():
            if self.active_nodes is not None:
                if (node_name in active_nodes) == (node_name in self.active_nodes):
                    # Skip publishing if hasn't changed
                    continue

            msg.data = bool(node_name in active_nodes)
            node_state = "ON" if msg.data else "OFF"
            node_pub.publish(msg)
            rospy.loginfo("[%s] Node %s set to %s." %(self.node_name, node_name, node_state))

        # Save current active nodes
        self.active_nodes = copy.deepcopy(active_nodes)

    def cbEvent(self,msg,event_name):
        if (msg.data):
            # Update timestamp
            rospy.loginfo("[%s] Event: %s" %(self.node_name,event_name))
            self.state_msg.header.stamp = msg.header.stamp
            next_state = self._getNextState(self.state_msg.state,event_name)
            if next_state is not None:
                # Has a defined transition
                self.state_msg.state = next_state
                self.publish()

    def on_shutdown(self):
        rospy.loginfo("[%s] Shutting down." %(self.node_name))

if __name__ == '__main__':
    # Initialize the node with rospy
    rospy.init_node('fsm_node', anonymous=False)

    # Create the NodeName object
    node = FSMNode()

    # Setup proper shutdown behavior 
    rospy.on_shutdown(node.on_shutdown)
    # Keep it spinning to keep the node alive
    rospy.spin()
