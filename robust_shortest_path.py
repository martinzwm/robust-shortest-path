'''
********************************************************
* The model shows a Benders Decomposition for a stochasitic programming coffee machine management problem.*

* The original MIP is decomposed into two problems.                           *

* The subproblem is using the dual formulation.            			*

* For consistency, this is built using an equivalent AMPL model coffee.run    *

#********************************************************
'''


from gurobipy import *
#from pygraphviz import *
#import math
from decimal import *
import copy
import random
import numpy as np
import sys

class RSP:
    
    def __init__(self, N, s, t, l, u):        
        # upper and lower bound on the arc length, square matrix of size N
        self.N = N
        self.u = u
        self.l = l

        self.s = s # Source node
        self.t = t # Destination node
        
        self.sm = Model('SubProblem')
        self.sm.setParam( 'OutputFlag', 0 ) 
        self.sm.setParam( 'LogToConsole', 0 )
        self.sm.setParam( 'LogFile', "" )   
        self.sm.params.threads = 1
        self.sm.params.NodefileStart = 0.5
        self.sm.params.timeLimit = 1800
        self.sm.params.DualReductions = 0   #turn off to avoid the optimization status of INF_OR_UNBD
        self.sm.params.InfUnbdInfo = 1  #Additional info for infeasible/unbounded models
        self.sm.ModelSense = -1  #sub problem is a maximization problem
        
        
        self.mm = Model('MasterProblem')
        self.mm.setParam( 'OutputFlag', 0 ) 
        self.mm.setParam( 'LogToConsole', 0 )
        self.mm.setParam( 'LogFile', "" )   
        self.mm.params.threads = 1
        self.mm.params.NodefileStart = 0.5
        self.mm.params.timeLimit = 1800
        self.mm.params.DualReductions = 0   #turn off to avoid the optimization status of INF_OR_UNBD
        self.mm.params.InfUnbdInfo = 1  #Additional info for infeasible/unbounded models
        
    def Sub_problem(self, Y):
        
        # Generate the sub problem dual problem
        self.w = {}
        
        self.sm.reset()
        for v in self.sm.getVars():
            self.sm.remove(v)
        for c in self.sm.getConstrs():
            self.sm.remove(c)        
          
        for i in range(self.N):
            for j in range(self.N):
                self.w[i,j] = self.sm.addVar(name='w_%s_%s' % (i, j), obj = -(self.l[i][j] + (self.u[i][j] - self.l[i][j]) * Y[i,j]), lb = 0, ub = 1)
                
        self.sm.update()
        
        for j in range(self.N):
            if j == self.s: # source node flux = -1
                self.sm.addConstr(sum(self.w[j,k] for k in range(self.N)) - 
                                  sum(self.w[i,j] for i in range(self.N)) == 1)
            elif j == self.t: # destination node flux = -1
                self.sm.addConstr(sum(self.w[j,k] for k in range(self.N)) - 
                                  sum(self.w[i,j] for i in range(self.N)) == -1)
            else: # intermediate node flux = 0
                self.sm.addConstr(sum(self.w[j,k] for k in range(self.N)) - 
                                  sum(self.w[i,j] for i in range(self.N)) == 0)
                
        self.sm.update()
    
        
    def Master_problem(self, nCut, cut_type, w_c_k, c_m_k):
    
        #Generate the Master Problem        
        self.mm.reset()
        for v in self.mm.getVars():
            self.mm.remove(v)
        for c in self.mm.getConstrs():
            self.mm.remove(c) 
            
        self.y = {}
        
        for i in range(self.N):
            for j in range(self.N):
                self.y[i,j] = self.mm.addVar(name='y_%s_%s' % (i, j), 
                      obj = 0, vtype=GRB.BINARY)
        
        self.z = self.mm.addVar(name ='z', obj = 1)
        
        self.mm.update()
        
        # For each cut found through the subproblem
        for k in range(1, nCut+1):
            if cut_type[k] == "point":
                self.mm.addConstr(self.z >= sum(self.u[i][j]*self.y[i,j]
                    for i in range(self.N) for j in range(self.N))
                    - sum((self.l[i][j]+(self.u[i][j]-self.l[i][j])*self.y[i,j])*w_c_k[i,j,k] 
                    for i in range(self.N) for j in range(self.N)))
        
        # Constraints based on node flux
        for j in range(self.N):
            if j == self.s: # source node flux = -1
                self.mm.addConstr(sum(self.y[j,k] for k in range(self.N)) - 
                                  sum(self.y[i,j] for i in range(self.N)) == 1)
            elif j == self.t: # destination node flux = -1
                self.mm.addConstr(sum(self.y[j,k] for k in range(self.N)) - 
                                  sum(self.y[i,j] for i in range(self.N)) == -1)
            else: # intermediate node flux = 0
                self.mm.addConstr(sum(self.y[j,k] for k in range(self.N)) - 
                                  sum(self.y[i,j] for i in range(self.N)) == 0)
         
        # Constraints to prevent self loop
        for i in range(self.N):
            self.mm.addConstr(self.y[i,i] == 0)
            
        self.mm.update()


def Benders_decomposition():
    
    s = 0
    t = 4
    
    # set seed to get consistent/comparable results
    np.random.seed(1234) 
    
    N = 100 # number of nodes in the graph
    M = 10000 # a very large number
    
    # Generate lower bound and upper bound
    # The graph should be directed because for traffic simulation
    # time from i to j could be vastly different than time from j to i
    l = np.random.randint(low=1, high=10, size=(N,N))
    u = np.random.randint(low=20, high=30, size=(N,N))
    
    # Diaganol should be 0 as it represent a self loop for a node
    for i in range(N):
        l[i][i] = 0
        u[i][i] = 0
    
    # The graph may not be fully connected, thus, should delete some path
    # Say the graph is 50% fully connected, set the weight of 50% of the
    # path to a very large number M.
    # The degree of connectivity in the graph is an adjustable parameter
    dummy = np.random.randint(low=0, high=10, size=(N,N)) # matrix of 0 and 1
    # For dummy = 1, keep path; otherwise, delete (set weight = M)
    for i in range(N):
        for j in range(N):
            if dummy[i][j] != 0:
                l[i][j] = M
                u[i][j] = M 
      
    print('visualize the graph')
    print('lower bound: \n')
    print(l)
    print('\n')
    print('upper bound: \n')
    print(u)
    print('\n')
    
    
    CMMP = RSP(N, s, t, l, u)
    
    #initialization
    nCut = 0
    z = -100
    Y = {}
    for i in range(N):
        for j in range(N):
            Y[i,j] = 0
            
    gap = float('inf')
    
    cut_type = {}
    
    w = {}
    w_c_k = {}
    
     
    
    #Benders decomposition procedure
    
    while True:
        
#        print ("\n Iteration %s") % (nCut + 1)
        #create subproblems
        CMMP.Sub_problem(Y)           
        
        try:
            
            CMMP.sm.optimize()
            
            
            if CMMP.sm.status == 5:
                print ("Unbounded")
                break
                        
            elif CMMP.sm.status == 2 or CMMP.sm.status == 9:
                dual_cost = CMMP.sm.ObjVal + sum(u[i][j]*Y[i,j] for i in range(N) for j in range(N))
                gap = min(gap, dual_cost - z)
                print(dual_cost, z)
                if dual_cost <= z + 0.00001:
                    break
                
                nCut += 1
                cut_type[nCut] = "point"
            
                for i in range(N):
                    for j in range(N):
                        w[i, j] = CMMP.sm.getVarByName('w_%s_%s' % (i, j))
            
                #get the unboundedness direction of the variable and add cuts
                for i in range(N):
                    for j in range(N):                
                        w_c_k[i, j, nCut] =  w[i, j].x #CMMP.sm.getAttr('x', lambda_c[i, j])
                
            
        except:
            print ("Sub problem solve error")
            break
        
        print ("Re-solve Master Problem")
        
        c_m_k = []
        for i in range(N):
            for j in range(N):
                for k in range(1, nCut+1):
                    c_m_k.append((i, j, k))
                        
        c_m_k = tuplelist(c_m_k)
            
        #create master roblems
        CMMP.Master_problem(nCut, cut_type, w_c_k, c_m_k)           
        
        try:
            
            CMMP.mm.optimize()
            
            for i in range(N):
                for j in range(N):
                    Y[i,j] = int(CMMP.mm.getVarByName('y_%s_%s' % (i, j)).x)
            z = CMMP.mm.getVarByName('z').x
            
            print('Matrix Y: ')
            print(print_Y(Y,N))
            print('\n')
            print('Matrix w: ')
            print(print_w(w,N))
            print('\n')
            print('z = ', z)
            print('\n')
            print('dual_cost = ', dual_cost)
            
            
        except:
            print ("Master problem error")
            break
        
    print(Y)    

# Functions for debugging     
def print_Y(Y, N):
    matrix = np.zeros([N,N])
    for i in range(N):
        for j in range(N):
            matrix[i][j] = Y[i,j]
    return matrix

def print_w(w,N):
    matrix = np.zeros([N,N])
    for i in range(N):
        for j in range(N):
            matrix[i][j] = w[i,j].x
    return matrix

            
if __name__ == '__main__':
    
    Benders_decomposition()
    
    