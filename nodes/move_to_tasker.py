#!/usr/bin/env python3
# encoding: utf8

import sys
import time

import rospy
import smach
import smach_ros

import rcprg_smach.conversation
import rcprg_smach.navigation

import rcprg_kb.places_xml as kb_p

from rcprg_smach.task_manager import PoseDescription

from pl_nouns.dictionary_client import DisctionaryServiceClient

from TaskER.TaskER import TaskER
from TaskER.dynamic_agent import DynAgent
from tasker_msgs.msg import RobotResource, ScheduleParams
from tasker_msgs.srv import SuspendConditionsRequest, SuspendConditionsResponse
from tasker_msgs.srv import CostConditionsRequest, CostConditionsResponse
# for ExeSuspension state
import subprocess
import imp

RUNIntrospectionServer = False

def ptf_csp(ptf_id):
    print "calculating SP: ", ptf_id
    # set flag 'self-terminate' to terminate DA if in Wait or Init state
    flag = None
    if ptf_id[0] == "scheduleParams":
        return [flag, ScheduleParams(cost = 10, completion_time=1,cost_per_sec=1,final_resource_state=RobotResource())]
    elif ptf_id[0] == "suspendCondition":
        req = SuspendConditionsRequest()
        req = ptf_id[1]
        return [flag, SuspendConditionsResponse(cost_per_sec=1, cost_to_resume=1)]
    elif ptf_id[0] == "startCondition":
        req = CostConditionsRequest()
        req = ptf_id[1]
        return [flag, CostConditionsResponse(cost_per_sec=1, cost_to_complete=1)]
class MyTaskER(TaskER):
    def __init__(self,da_state_name, da_name):
        self.name = unicode(da_name)
        rospy.init_node(self.name)
        self.sim_mode = None
        self.conversation_interface = None
        self.kb_places = None
        TaskER.__init__(self,da_state_name)
        if RUNIntrospectionServer:
            self.sis = smach_ros.IntrospectionServer(unicode(str("/"+self.name+"smach_view_server")), self, unicode(self.name))
            self.sis.start()
        places_xml_filename = rospy.get_param('/kb_places_xml')
        self.sim_mode = str(rospy.get_param('/sim_mode'))
        assert self.sim_mode in ['sim', 'gazebo', 'real']

        print 'Reading KB for places from file "' + places_xml_filename + '"'
        self.kb_places = kb_p.PlacesXmlParser(places_xml_filename).getKB()


        self.conversation_interface = rcprg_smach.conversation.ConversationMachine([
                ('ack',             'projects/incare-dialog-agent/agent/intents/ef92199b-d298-470c-8df3-1e1047dd70d1'),
                ('ack_i_took',      'ack_i_took'),
                ('ack_i_gave',      'ack_i_gave'),
                ('q_current_task',  'projects/incare-dialog-agent/agent/intents/8f45359d-ee47-4e10-a1b2-de3f3223e5b4'),
                ('q_load',          'projects/incare-dialog-agent/agent/intents/b8743ab9-08a1-49e8-a534-abb65155c507'),
                ('turn_around',     'projects/incare-dialog-agent/agent/intents/b4cb9f2e-2589-44dd-af14-a8f899c40ec0'),
            ], self.sim_mode)

        if len(sys.argv) < 3:
            raise Exception('Too few arguments: ' + str(sys.argv))

        place_name = None
        for idx in range(1, len(sys.argv), 2):
            if sys.argv[idx] == 'miejsce':
                place_name = sys.argv[idx+1] 

        if isinstance(place_name, str):
            place_name = place_name.decode('utf-8')
        place_name = place_name.encode('utf-8').decode('utf-8')

        dictionary = DisctionaryServiceClient()
        place_name_m = dictionary.getCases(place_name).getCase('mianownik')
        self.userdata.goal = PoseDescription({'place_name': place_name_m})
        self.userdata.fsm_es = ""

        if self.sim_mode == 'real':
            mc_name = 'real'
        elif self.sim_mode == 'gazebo':
            mc_name = 'sim'
            
        print 'get place: ', place_name_m
        pl = self.kb_places.getPlaceByName(place_name_m, mc_name)

        if pl.isDestinationHuman():
            self.my_fsm = rcprg_smach.navigation.MoveToHumanComplex(self.sim_mode, self.conversation_interface, self.kb_places)
        else:
            self.my_fsm = rcprg_smach.navigation.MoveToComplex(self.sim_mode, self.conversation_interface, self.kb_places)

    def shutdownRequest(self):
        print ("my-tasker -----------------------   shutdown")
        self.conversation_interface.stop()
        if RUNIntrospectionServer:
            self.sis.stop()
            self.sis.clear()
        
    def cleanup_tf(self):
        rospy.loginfo('{}: Executing state: {}'.format(rospy.get_name(), self.__class__.__name__))
        print 'Cleanup.execute'
        self.conversation_interface.stop()
        return 'ok'

    def get_suspension_tf(self,susp_data):
        print "My TASKER -- get_suspension_tf"
        print "My TASKER"
        print "My TASKER"
        rospy.loginfo('{}: Executing state: {}'.format(rospy.get_name(), self.__class__.__name__))
        print 'GetSuspend.execute'
        print "susp data: ", susp_data.getData()
        print "susp data[0]: ", susp_data.getData()[0]
        data = susp_data.getData()
        fsm_executable = None
        for idx in range(2, len(data), 2):
            # print data[idx]
            if data[idx] == 'executable':
                fsm_executable = data[idx+1]
            elif data[idx] == 'rosrun':
                ros_pkg = data[idx+1]
                ros_exec = data[idx+2]
                fsm_executable = "rosrun "+ros_pkg+" "+ros_exec
        if fsm_executable == None:
            print "harmoniser did not specified executable for suspension behaviour, terminating task"
            fsm_executable = "terminate task"
        return fsm_executable

    def exe_suspension_tf(self,fsm_es_in):
        print "My TASKER -- exe_suspension_tf"
        print "My TASKER"
        print "My TASKER"
        rospy.loginfo('{}: Executing state: {}'.format(rospy.get_name(), self.__class__.__name__))
        print 'ExecSuspension.execute'
        #srv.shutdown()
        print fsm_es_in
        if fsm_es_in == "terminate task":
            return 'shutdown'
        else:
            p = subprocess.Popen(fsm_es_in , shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # and you can block util the cmd execute finish
            p.wait()
        return 'FINISHED'
    def wait_tf(self):
        print "My TASKER -- wait_tf"
        print "My TASKER"
        print "My TASKER"
        pass
    def update_task_tf(self):
        print "My TASKER -- update_task_tf"
        print "My TASKER"
        print "My TASKER"
        if RUNIntrospectionServer:
            self.sis.stop()
            self.sis.clear()

        # imp.reload(tiago_smach.human_fell)
        print "SWAPPING"
        if self.sim_mode == 'real':
            mc_name = 'real'
        elif self.sim_mode == 'gazebo':
            mc_name = 'sim'
        pl = self.kb_places.getPlaceByName(self.userdata.goal.parameters['place_name'], mc_name)
        if pl.isDestinationHuman():
            self.swap_state('ExecFSM', rcprg_smach.navigation.MoveToHumanComplex(self.sim_mode, self.conversation_interface, self.kb_places))
        else:
            self.swap_state('ExecFSM', rcprg_smach.navigation.MoveToComplex(self.sim_mode, self.conversation_interface, self.kb_places))
        if RUNIntrospectionServer:
            self.sis.start()
        # self.my_fsm.set_initial_state(['MoveToKitchen'])
        pass
    def initialise_tf(self):
        print "My TASKER -- initialise"
        self.conversation_interface.start()

def main():
    da_name = None
    da_type = None
    da_id = None
    da_state_name = []
    for idx in range(1, len(sys.argv), 2):
                if sys.argv[idx] == 'da_name':
                    da_name = sys.argv[idx+1]
                if sys.argv[idx] == 'da_type':
                    da_type = sys.argv[idx+1]
                if sys.argv[idx] == 'da_id':
                    da_id = sys.argv[idx+1]
    if da_name == None or da_type == None or da_id == None:
        print "DA: one of the parameters (<da_name>, <da_type>, or <da_id>) is not specified"
        return 1
    da = DynAgent( da_name, da_id, da_type, ptf_csp, da_state_name )
    print "RUN BRING"
    da.run( MyTaskER(da_state_name,da_name) )
    print "BG ENDED"
    return 0

if __name__ == '__main__':
    main()
    print "ALLLLLLL CLOOOOOSSSSEEEEED"
