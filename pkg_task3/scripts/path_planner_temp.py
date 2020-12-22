#!/usr/bin/env python

import rospy
import math
from sensor_msgs.msg import NavSatFix, LaserScan, Imu


class PathPlanner():

    def __init__(self):
        rospy.init_node('path_planner_beta')

        # Destination to be reached
        # [latitude, longitude, altitude]
        self.destination = [[18.9990965928, 72.0000664814, 10.75],
                            [18.9990965925, 71.9999050292, 22.2],
                            [18.9993675932, 72.0000569892, 10.7]]
        # Converting latitude and longitude in meters for calculation
        self.destination_xy = [0, 0]

        # Present Location of the DroneNote
        self.current_location = [0, 0, 0]
        # Converting latitude and longitude in meters for calculation
        self.current_location_xy = [0, 0]

        # The checkpoint node to be reached for reaching final destination
        self.checkpoint = NavSatFix()

        # Initializing to store data from Lazer Sensors
        self.obs_range_top = []
        # self.obs_range_bottom = []

        # Defining variables which are needed for calculation
        # diffrence of current and final position
        self.diff_xy = [0, 0]
        self.distance_xy = 0                # distance between current and final position

        self.movement_in_1D = 0             # maximum movement to be done in one direction
        # [x, y] -> movement distribution in x and y
        self.movement_in_plane = [0, 0]
        # closest distance of obstacle (in meters)
        self.obs_closest_range = 8

        self.sample_time = 0.01

        # Publisher
        self.pub_checkpoint = rospy.Publisher('/checkpoint', NavSatFix, queue_size=1)
        self.pub_err_x_m = rospy.Publisher('/edrone/err_x_m', Float, queue_size=1)
        self.pub_err_y_m = rospy.Publisher('/edrone/err_y_m', Float, queue_size=1)

        # Subscriber
        # rospy.Subscriber('/final_setpoint', NavSatFix, self.final_setpoint_callback)
        rospy.Subscriber('/edrone/gps', NavSatFix, self.gps_callback)
        rospy.Subscriber('/edrone/range_finder_top', LaserScan, self.range_finder_top_callback)
        rospy.Subscriber('/marker_error', NavSatFix, self.marker_error_callback)
        rospy.Subscriber('/edrone/range_finder_bottom', LaserScan, self.range_finder_bottom_callback)

    def final_setpoint_callback(self, msg):
        self.destination = [msg.latitude, msg.longitude, msg.altitude]

    def gps_callback(self, msg):
        self.current_location = [msg.latitude, msg.longitude, msg.altitude]

    def range_finder_top_callback(self, msg):
        self.obs_range_top = msg.ranges

    # def range_finder_bottom_callback(self, msg):
    #     self.obs_range_bottom = msg.ranges

    # Functions for data conversion between GPS and meter with respect to origin
    def lat_to_x(self, input_latitude): return 110692.0702932625 * (input_latitude - 19)
    def long_to_y(self, input_longitude): return - 105292.0089353767 * (input_longitude - 72)

    def x_to_lat_diff(self, input_x): return (input_x / 110692.0702932625)
    def y_to_long_diff(self, input_y): return (input_y / -105292.0089353767)

    def calculate_movement_in_plane(self, total_movement):
        '''This Function will take the drone in straight line towards destination'''

        # movement in specific direction that is x and y
        specific_movement = [0, 0]

        # Applying symmetric triangle method
        specific_movement[0] = (total_movement * self.diff_xy[0]) / self.distance_xy
        specific_movement[1] = (total_movement * self.diff_xy[1]) / self.distance_xy
        return specific_movement

    def obstacle_avoid(self):
        '''For Processing the obtained sensor data and publishing required 
        checkpoint for avoiding obstacles'''

        if self.destination == [0, 0, 0]:
            return

        data = self.obs_range_top
        self.movement_in_plane = [0, 0]

        # destination in x and y form
        self.current_location_xy = [self.lat_to_x(self.destination[0]),
                                    self.long_to_y(self.destination[1])]

        self.destination_xy = [self.lat_to_x(self.current_location[0]),
                               self.long_to_y(self.current_location[1])]

        self.diff_xy = [self.destination_xy[0] - self.current_location_xy[0],
                        self.destination_xy[1] - self.current_location_xy[1]]

        self.distance_xy = math.hypot(self.diff_xy[0], self.diff_xy[1])

        # calculating maximum distance to be covered at once
        # it can be done more efficiently using another pid
        for obs_distance in data:
            if 16 <= obs_distance:
                self.movement_in_1D = 15
            elif 9 <= obs_distance:
                self.movement_in_1D = 4
            else:
                self.movement_in_1D = 2.5

        # checking if destination is nearer than maximum distance to be travelled
        if self.movement_in_1D >= self.distance_xy:
            self.movement_in_1D = self.distance_xy

        # doge the obstacle if its closer than certain distance
        for i in range(len(data)-1):
            if data[i] <= self.obs_closest_range:
                if i % 2 != 0:
                    self.movement_in_plane[0] = data[i] - self.obs_closest_range
                    self.movement_in_plane[1] = self.movement_in_1D
                else:
                    self.movement_in_plane[0] = self.movement_in_1D
                    self.movement_in_plane[1] = data[i] - self.obs_closest_range
            else:
                self.movement_in_plane = self.calculate_movement_in_plane(
                    self.movement_in_1D)

        # print(self.movement_in_plane,self.movement_in_1D)

        # setting the values to publish
        self.checkpoint.latitude = self.current_location[0] - self.x_to_lat_diff(self.movement_in_plane[0])
        self.checkpoint.longitude = self.current_location[1] - self.y_to_long_diff(self.movement_in_plane[1])
        # giving fixed altitude for now will work on it in future
        self.checkpoint.altitude = 24

        # Publishing
        self.pub_checkpoint.publish(self.checkpoint)

    def calculate_corners(self):
        corner_length = math.tan(1.3962634/2) * self.obs_range_bottom[0]
        corner_length_x = self.x_to_lat_diff(corner_length)
        corner_length_y = self.y_to_long_diff(corner_length)
        corner1 = [corner_length_x + self.current_location[0], corner_length_y + self.current_location[1]]
        corner2 = [corner_length_x + self.current_location[0], corner_length_y - self.current_location[1]]
        corner3 = [corner_length_x - self.current_location[0], corner_length_y + self.current_location[1]]
        corner4 = [corner_length_x - self.current_location[0], corner_length_y - self.current_location[1]]

        return [corner1, corner2, corner3, corner4]

    def marker_find(self):
        '''this is the algorithm to find landing marker'''

        '''TODO:
        1. maintain particular height
        2. see if marker is detected \
            if yes:
                --> calculate distance of marker from current position
                --> publish final setpoint
        3. calculate corners of obtained image and store it in list
        4. go to each place in the list, if reached building's edge then skip
        5. repeat from step 2 untill marker is found
        ''' 

        print("in the marker find")
        # declaring local variables
        bottom_height_error = self.obs_range_bottom[0] - self.definite_bottom_height
        edge_reached = False

        # Maintaining particular height from bottom and building edge detection 
        if bottom_height_error < self.edge_detection_height:
            if bottom_height_error >= 0:
                self.checkpoint.altitude = self.current_location[2] - bottom_height_error
            else:
                self.checkpoint.altitude = self.current_location[2] - bottom_height_error
        else:
            edge_reached = True

        # see if marker is detected
        if self.img_data[0] != 0:
            self.checkpoint.latitude += self.x_to_lat_diff(self.img_data[0])
            self.checkpoint.longitude += self.y_to_long_diff(self.img_data[1])

            # Publish
            self.pub_checkpoint.publish(self.checkpoint)
            return

        # calculating corners of image
        if self.corner_counter == 0:
            self.corner_points = self.calculate_corners()

        self.checkpoint.latitude = self.corner_points[self.corner_counter][0]
        self.checkpoint.longitude = self.corner_points[self.corner_counter][1]

        self.pub_checkpoint.publish(self.checkpoint)

        return


if __name__ == "__main__":
    planner = PathPlanner()
    rate = rospy.Rate(1/planner.sample_time)
    while not rospy.is_shutdown():
        planner.obstacle_avoid()
        rate.sleep()