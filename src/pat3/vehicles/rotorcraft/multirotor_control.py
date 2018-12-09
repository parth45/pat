#! /usr/bin/env python
#-*- coding: utf-8 -*-

import math, numpy as np, matplotlib.pyplot as plt
import pdb
import pat3.algebra as pal
import pat3.plot_utils as ppu
import pat3.vehicles.rotorcraft.multirotor_fdm as fdm

# /media/mint17/home/poine/dissertation/exemples/guidage_d_un_drone_a_poussee_vectorielle/control.py
# /media/mint17/home/poine/dissertation/obsolete/guidage_quad_multirotors.tex

iv_z, iv_qi, iv_qx, iv_qy, iv_qz = range(5)
iv_size = 5

def step(t, a=-1., p=10., dt=0.): return a if math.fmod(t+dt, p) > p/2 else -a

class StepZInput:
    def __init__(self, _a=1):
        self._a = _a
        
    def get(self, t): return [step(t, self._a), 1, 0, 0, 0]

class SinZInput:
    def get(self, t): return [0.5*np.sin(t), 1, 0, 0, 0]

class StepEulerInput:
    def __init__(self, _i, _a=np.deg2rad(1.), p=10, dt=5):
        self._i, self._a, self._p, self.dt = _i, _a, p, dt
        
    def get(self, t):
        eu = [0, 0, 0]
        eu[self._i] = step(t, self._a, self._p, self.dt)
        zc, qc = [0], pal.quat_of_euler(eu)
        return np.append(zc, qc)

class StepEulerInput2:
    def __init__(self, _i, _a=np.deg2rad(1.), p=10, dt=5):
        self._i, self._a, self._p, self.dt = _i, _a, p, dt

    def get(self, t):
        pass

        
    
class CstInput:
    def __init__(self, z, eu):
        self.z = z
        self.q = pal.quat_of_euler(eu)
        
    def get(self, t):
        return np.append(self.z, self.q)

class RandomInput:
    def __init__(self, pulse_len=2.):
        self.pulse_len = pulse_len
        self.next_pulse_t = None
    
    def get(self, t):
        if self.next_pulse_t is None: self.next_pulse_t = t
        if t >= self.next_pulse_t:
            zc = [np.random.uniform(low=-1, high=1.)]
            phic, thetac = np.random.uniform(low=-np.deg2rad(0.5), high=np.deg2rad(0.5), size=2)
            psic = np.random.uniform(low=-np.pi, high=np.pi)
            qc = pal.quat_of_euler([phic, thetac, psic])
            self.Yc = np.append(zc, qc)
            self.next_pulse_t += self.pulse_len
        return self.Yc

class ZAttController:

    def __init__(self, fdm):
        self.Xe, self.Ue = fdm.trim()
        self.z_ctl = Zctl(self.Ue, self.Xe)
        self.att_ctl = AttCtl(fdm.P)
        self.H = np.array([[0.25, -1,  1, -1],
                           [0.25, -1, -1,  1],
                           [0.25,  1, -1, -1],
                           [0.25,  1,  1,  1]])
        self.invH = np.linalg.inv(self.H)
        
    def get(self, X, Yc):
        zc, qc = Yc[0], Yc[1:]
        Uz = self.z_ctl.run(X, zc)
        Upqr = self.att_ctl.run(X, qc)
        U = np.dot(self.H, np.hstack((Uz, Upqr)))
        #pdb.set_trace()
        return U

    def plot(self, time, Yc, U=None, figure=None, window_title="Trajectory"):
        if figure is None: figure = plt.gcf()
        plt.subplot(5, 3, 3)
        plt.plot(time, Yc[:,0], lw=2., label='setpoint')
        euler_c = np.array([pal.euler_of_quat(_sp[1:]) for _sp in Yc])
        plt.subplot(5, 3, 7)
        plt.plot(time, np.rad2deg(euler_c[:,0]), label='setpoint')
        plt.subplot(5, 3, 8)
        plt.plot(time, np.rad2deg(euler_c[:,1]), label='setpoint')
        plt.subplot(5, 3, 9)
        plt.plot(time, np.rad2deg(euler_c[:,2]), label='setpoint')
        Uzpqr = np.array([np.dot(self.invH, Uk) for Uk in U])
        ax = plt.subplot(5, 3, 14)
        plt.plot(time, Uzpqr[:,0], label='Uz')
        ppu.decorate(ax, title='$U_z$', xlab='s', ylab='N', legend=True)
        ax = plt.subplot(5, 3, 15)
        plt.plot(time, Uzpqr[:,1], label='Up')
        plt.plot(time, Uzpqr[:,2], label='Uq')
        plt.plot(time, Uzpqr[:,3], label='Ur')
        ppu.decorate(ax, title='$U_{pqr}$', xlab='s', ylab='N', legend=True)
        return figure
        
        
    

class Zctl:
    def __init__(self, Ue, Xe):
        self.Fez, self.Xe = np.sum(Ue), Xe
        self.K = [[0, 0, -1.5,  0, 0, -1.5,  0, 0, 0, 0,  0, 0, 0]]
        self.H = np.array([-1.5])

    def run(self, X, zc):
        Fbz = self.Fez - np.dot(self.K, X-self.Xe) + np.dot(self.H, [zc])
        return Fbz


class AttCtl:
    def __init__(self, P):
        self.P = P           # dynamic model parameters
        self.ref = AttRef()
        self.omega = np.array([20., 20., 15.])
        self.xi = np.array([0.7, 0.7, 0.7])
            
    def run(self, X, qref=[1, 0, 0, 0], rvel_ref=[0, 0, 0]):
        # error quaternion
        err_quat = pal.quat_inv_comp(X[fdm.sv_slice_quat], qref)
        err_quat = pal.quat_wrap_shortest(err_quat)
        # rotational velocities
        delta_rvel = X[fdm.sv_slice_rvel] - rvel_ref
        # rotational acceleration
        racc = -2*self.omega*self.xi*delta_rvel + self.omega**2 * err_quat[pal.q_x:pal.q_z+1]
        #
        Jxx, Jyy, Jzz = np.diag(self.P.J)
        tmp = np.array([(Jzz-Jyy)/Jxx*X[fdm.sv_q]*X[fdm.sv_r],
                        (Jxx-Jzz)/Jyy*X[fdm.sv_p]*X[fdm.sv_r],
                        (Jyy-Jxx)/Jzz*X[fdm.sv_p]*X[fdm.sv_q]]);
        # inertia
        J = np.array([Jxx/self.P.l, Jyy/self.P.l, Jzz/self.P.k])
        Upqr = J * ( racc  + tmp )
        return Upqr


        
class AttRef:
    def __init__(self):
        self.q = pal.quat_null()


    def run(self, pqr_sp, dt):
        self.q = pal.quat_integrate(self.q, pqr_sp, dt)
        self.om = pqr_sp



#
# Differential Flatness
#
_x, _y, _z, _psi = range(4)
class DiffFlatness:

    def state_and_cmd_of_flat_output(self, Y, P):
        #pdb.set_trace()
        wind = np.zeros(3)
        cd_ov_m = 0.2/P.m #param[prm_Cd]/param[prm_mass]
        a0 = np.array([
            Y[_x, 2] + cd_ov_m*(Y[_x, 1] - wind[_x]),
            Y[_y, 2] + cd_ov_m*(Y[_y, 1] - wind[_y]),
            Y[_z, 2] + cd_ov_m*(Y[_z, 1] - wind[_z]) - 9.81 ])
        a1 = np.array([
            Y[_x, 3] + cd_ov_m*Y[_x, 2],
            Y[_y, 3] + cd_ov_m*Y[_y, 2],
            Y[_z, 3] + cd_ov_m*Y[_z, 2] ])
        a2 = np.array([
            Y[_x, 4] + cd_ov_m*Y[_x, 3],
            Y[_y, 4] + cd_ov_m*Y[_y, 3],
            Y[_z, 4] + cd_ov_m*Y[_z, 3] ])
        psi = Y[_psi, 0]
        cpsi, spsi = np.cos(psi), np.sin(psi)
        psi1 = Y[_psi, 1]
        psi2 = Y[_psi, 2]
        b0 = np.array([
            cpsi*a0[_x] + spsi*a0[_y],
            -spsi*a0[_x] + cpsi*a0[_y],
             a0[_z]
        ])
        b1 = np.array([
            cpsi*a1[_x] + spsi*a1[_y] - psi1*(spsi*a0[_x] - cpsi*a0[_y]),
            -spsi*a1[_x] + cpsi*a1[_y] - psi1*(cpsi*a0[_x] + spsi*a0[_y]),
            a1[_z]
        ])
        b2 = np.array([
            cpsi*a2[_x] + spsi*a2[_y] - 2*psi1*(spsi*a1[_x] - cpsi*a1[_y])
            +(-psi2*spsi-psi1**2*cpsi)*a0[_x] + ( psi2*cpsi-psi1**2*spsi)*a0[_y],
            -spsi*a2[_x] + cpsi*a2[_y] - 2*psi1*(cpsi*a1[_x] + spsi*a1[_y])
            +(-psi2*cpsi+psi1**2*spsi)*a0[_x] + (-psi2*spsi-psi1**2*cpsi)*a0[_y],
            a2[_z]
        ])

        c0 = math.sqrt(b0[_x]**2+b0[_z]**2)
        c1 = (b0[_x]*b1[_x]+ b0[_z]*b1[_z])/c0
        c2 = (b1[_x]**2 + b0[_x]*b2[_x] + b1[_z]**2 + b0[_z]*b2[_z] - c1**2)/c0
        n2a = a0[_x]**2 + a0[_y]**2 + a0[_z]**2
        na = math.sqrt(n2a)

        # euler
        phi0   = -np.sign(b0[_z])*math.atan(b0[_y]/c0)
        theta0 = math.atan(b0[_x]/b0[_z])
        # euler dot
        phi1   = (b1[_y]*c0-b0[_y]*c1)/n2a           # checked
        theta1 = (b1[_x]*b0[_z]-b0[_x]*b1[_z])/c0**2   # checked
        # rvel
        cph = math.cos(phi0)
        sph = math.sin(phi0)
        cth = math.cos(theta0)
        sth = math.sin(theta0)
        p =  phi1 - sth*psi1
        q =  cph*theta1 + sph*cth*psi1
        r = -sph*theta1 + cph*cth*psi1
        # euler dot dot
        phi2   = (b2[_y]*c0 - b0[_y]*c2)/na**2 \
                 -2*(b1[_y]*c0-b0[_y]*c1)*(b0[_x]*b1[_x]+b0[_y]*b1[_y]+b0[_z]*b1[_z])/na**4 # checked
        theta2 = (b2[_x]*b0[_z] - b0[_x]*b2[_z])/c0**2 \
                 -2*(b1[_x]*b0[_z] - b0[_x]*b1[_z])*(b0[_x]*b1[_x]+b0[_z]*b1[_z])/c0**4 # checked
        # raccel
        p1 = phi2 - cth*theta1*psi1 - sth*psi2
        q1 = -sph*phi1*theta1 +cph*theta2 +cph*cth*phi1*psi1 -sph*sth*theta1*psi1 +sph*cth*psi2
        r1 = -cph*phi1*theta1 -sph*theta2 -sph*cth*phi1*psi1 -cph*sth*theta1*psi1 +cph*cth*psi2


        _q = pal.quat_of_euler([phi0, theta0, psi])
        X = np.array([Y[_x, 0], Y[_y, 0], Y[_z, 0],
                      Y[_x, 1], Y[_y, 1], Y[_z, 1],
                      _q[0], _q[1], _q[2], _q[3],
                      p, q, r ])
        Ut = na*P.m
        Jxx, Jyy, Jzz = np.diag(P.J)
        Up = Jxx/P.l * p1 + (Jzz-Jyy)/P.l*q*r
        Uq = Jyy/P.l * q1 + (Jxx-Jzz)/P.l*p*r
        Ur = Jzz/P.k * r1 + (Jyy-Jxx)/P.k*p*q
        U = np.array([Ut, Up, Uq, Ur])
        
        return X, U
