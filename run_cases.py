import sys
try:
    import cantera as ct
except ImportError:
    print("Cantera must be installed")
    sys.exit(1)
    
try:    
    import numpy as np
except ImportError:
    print('Numpy must be installed')
    sys.exit(1)

try:
    import tables
except ImportError:
    print('PyTables must be installed')
    sys.exit(1)

import printer
import utils

class SimulationCase(object):
    def __init__(self, filenames, convert):
        self.input_filename = filenames[0]
        self.mech_filename = filenames[1]
        self.save_filename = filenames[2]
        
        if self.mech_filename.endswith('.inp'):
            self.mech_filename = utils.convert_mech(self.mech_filename, convert)
            
        self.keywords = utils.read_input_file(input_filename)
        
    def setup_case(self):
        gas = ct.Solution(self.mech_filename)

        initial_temp = self.keywords['temperature']
        initial_pres = self.keywords['pressure']*ct.one_atm
        if 'eqRatio' in self.keywords:
            reactants = utils.equivalence_ratio(self.gas,self.keywords['eqRatio'],self.keywords['fuel'],
                                          self.keywords['oxidizer'],
                                          self.keywords['completeProducts'],
                                          self.keywords['additionalSpecies'],
                                          )
        else:
            reactants = ','.join(self.keywords['reactants'])
        
        self.gas.TPX = initial_temp, initial_pres, reactants
        
        env = ct.Reservoir(ct.Solution('air.xml'))
        
        #Could refactor here to put the problem setup in another function and return the
        #reactor, n_vars, wall, and tempFunc.
        self.temp_func = None
        if self.keywords['problemType'] == 1:
            self.reac = ct.IdealGasReactor(gas)
            #Number of solution variables is number of species + mass, volume, temperature
            self.n_vars = self.reac.kinetics.n_species + 3
            self.wall = ct.Wall(self.reac,env,A=1.0,velocity=0)
        elif self.keywords['problemType'] == 2:
            self.reac = ct.IdealGasConstPressureReactor(gas)
            #Number of solution variables is number of species + mass, temperature
            self.n_vars = self.reac.kinetics.n_species + 2
            self.wall = ct.Wall(self.reac,env,A=1.0,velocity=0)
        elif self.keywords['problemType'] == 3:
            self.reac = ct.IdealGasReactor(gas)
            #Number of solution variables is number of species + mass, volume, temperature
            self.n_vars = self.reac.kinetics.n_species + 3
            self.wall = ct.Wall(self.reac,env,A=1.0,velocity=VolumeProfile(self.keywords))
        elif self.keywords['problemType'] == 4:
            self.reac = ct.IdealGasConstPressureReactor(gas,energy='off')
            #Number of solution variables is number of species + mass, temperature
            self.n_vars = self.reac.kinetics.n_species + 2
            self.wall = ct.Wall(self.reac,env,A=1.0,velocity=0)
        elif self.keywords['problemType'] == 5:
            self.reac = ct.IdealGasReactor(gas,energy='off')
            #Number of solution variables is number of species + mass, volume, temperature
            self.n_vars = self.reac.kinetics.n_species + 3
            self.wall = ct.Wall(self.reac,env,A=1.0,velocity=0)
        elif self.keywords['problemType'] == 6:
            from user_routines import VolumeFunctionTime
            self.reac = ct.IdealGasReactor(gas)
            #Number of solution variables is number of species + mass, volume, temperature
            self.n_vars = self.reac.kinetics.n_species + 3
            self.wall = ct.Wall(self.reac,env,A=1.0,velocity=VolumeFunctionTime())
        elif self.keywords['problemType'] == 7:
            from user_routines import TemperatureFunctionTime
            self.reac = ct.IdealGasConstPressureReactor(gas,energy='off')
            #Number of solution variables is number of species + mass, temperature
            self.n_vars = self.reac.kinetics.n_species + 2
            self.wall = ct.Wall(self.reac,env,A=1.0,velocity=0)
            tempFunc = ct.Func1(TemperatureFunctionTime())
        elif self.keywords['problemType'] == 8:
            self.reac = ct.IdealGasConstPressureReactor(gas,energy='off')
            #Number of solution variables is number of species + mass, temperature
            self.n_vars = self.reac.kinetics.n_species + 2
            self.wall = ct.Wall(self.reac,env,A=1.0,velocity=0)
            tempFunc = ct.Func1(TemperatureProfile(self.keywords))
        
        if 'reactorVolume' in self.keywords:
            self.reac.volume = self.keywords['reactorVolume']
            
        self.netw = ct.ReactorNet([self.reac])
                
        if 'sensitivity' in self.keywords:
            self.sensitivity = True
            for i in range(self.reac.kinetics.n_reactions):
                self.reac.add_sensitivity_reaction(i)
            if 'sensAbsTol' in self.keywords:
                self.netw.atol_sensitivity = self.keywords['sensAbsTol']
            else:
                self.netw.atol_sensitivity = 1.0E-06
            if 'sensRelTol' in self.keywords:
                self.netw.rtol_sensitivity = self.keywords['sensRelTol']
            else:
                self.netw.rtol_sensitivity = 1.0E-04
        else:
            self.sensitivity = False
        
        if 'abstol' in self.keywords:
            self.netw.atol = self.keywords['abstol']
        else:
            self.netw.atol = 1.0E-20
            
        if 'reltol' in self.keywords:
            self.netw.rtol = self.keywords['reltol']
        else:
            self.netw.rtol = 1.0E-08
        
        #return reac,netw,wall,n_vars,sensitivity,tempFunc

    def run_case(self):
        
        tend = keywords['endTime']
        
        if 'tempLimit' in keywords:
            tempLimit = keywords['tempLimit']
        else:
            #tempThresh is set in the parser even if it is not present in the input file
            tempLimit = keywords['tempThresh'] + keywords['temperature']
        
        printTimeInt = keywords.get('prntTimeInt')
        saveTimeInt = keywords.get('saveTimeInt')
        maxTimeInt = keywords.get('maxTimeStep')
        
        timeInts = [value for value in [printTimeInt,saveTimeInt,maxTimeInt] if value is not None]
        
        if timeInts:
            self.netw.set_max_time_step(min(timeInts))
        else:
            self.netw.set_max_time_step(tend/100)
        
        if printTimeInt is not None:
            printTimeStep = printTimeInt
        else:
            printTimeStep = tend/100
            
        saveTimeStep = saveTimeInt

        printTime = printTimeStep
        
        if saveTimeStep is not None:
            saveTime = saveTimeStep
            
        tableDef = {'time':tables.Float64Col(pos=0),
                   'temperature':tables.Float64Col(pos=1),
                   'pressure':tables.Float64Col(pos=2),
                   'volume':tables.Float64Col(pos=3),
                   'massfractions':tables.Float64Col(shape=(self.reac.thermo.n_species),pos=4),
                   }
        if self.sensitivity:
            tableDef['sensitivity'] = tables.Float64Col(shape=(self.n_vars,self.netw.n_sensitivity_params),pos=5)
            
        species_names = self.reac.thermo.species_names
        
        #Use the table format of hdf instead of the array format. This way, each variable can be saved 
        #in its own column and referenced individually when read. Solution to the interpolation problem 
        #was made by saving each time step into a numpy array. The arrays are not vertically appended
        #so we should eliminate the hassle associated with that.
        with tables.open_file(saveFilename, mode = 'w', title = 'CanSen Save File') as saveFile:
            table = saveFile.create_table(saveFile.root, 'reactor', tableDef, 'Reactor State')
            
            timestep = table.row
            timestep['time'] = self.netw.time
            timestep['temperature'],timestep['pressure'],timestep['massfractions'] = self.reac.thermo.TPY
            timestep['volume'] = self.reac.volume
            if self.sensitivity:
                timestep['sensitivity'] = np.zeros((self.n_vars,self.netw.n_sensitivity_params))
            timestep.append()
            table.flush()
            
            prevTime = np.hstack((self.netw.time, self.reac.thermo.T, self.reac.thermo.P, self.reac.volume, self.wall.vdot(self.netw.time), self.reac.thermo.X))
            
            print(printer.divider)
            print('Kinetic Mechanism Details:\n')
            print('Total Gas Phase Species     = {0}\n'.format(self.reac.kinetics.n_species),
                  'Total Gas Phase Reactions   = {0}'.format(self.reac.kinetics.n_reactions),
                  sep='')
            if self.sensitivity:
                print('Total Sensitivity Reactions = {}'.format(self.netw.n_sensitivity_params))
            print(printer.divider,'\n')
            
            printer.reactor_state_printer(prevTime,species_names)
            
            while self.netw.time < tend:
            
                if tempFunc is not None:
                    gas.TP = tempFunc(self.netw.time), None
                    
                self.netw.step(tend)
                curTime = np.hstack((self.netw.time, self.reac.thermo.T, self.reac.thermo.P, self.reac.volume, self.wall.vdot(self.netw.time), self.reac.thermo.X))
                
                if self.netw.time > tend:
                    interpState = utils.reactor_interpolate(tend,prevTime,curTime)
                    printer.reactor_state_printer(interpState,species_names,end=True)
                    timestep['time'] = tend
                    timestep['temperature'] = interpState[1]
                    timestep['pressure'] = interpState[2]
                    timestep['massfractions'] = interpState[5:] * self.reac.thermo.molecular_weights/self.reac.thermo.mean_molecular_weight
                    timestep['volume'] = interpState[3]
                    if self.sensitivity:
                        #Add sensitivity interpolation here by reading from file on disk. Only have to do it once, so shouldn't be
                        #too expensive
                        pass
                    break
                    
                if saveTimeStep is not None:
                    pass
                else:
                    timestep['time'] = self.netw.time
                    timestep['temperature'],timestep['pressure'],timestep['massfractions'] = self.reac.thermo.TPY
                    timestep['volume'] = self.reac.volume
                    if self.sensitivity:
                        timestep['sensitivity'] = self.netw.sensitivities()
                    timestep.append()
                    table.flush()
                    
                if self.netw.time > printTime:
                    interpState = utils.reactor_interpolate(printTime,prevTime,curTime)
                    printer.reactor_state_printer(interpState,species_names)
                    printTime += printTimeStep
                elif self.netw.time == printTime:
                    printer.reactor_state_printer(curTime,species_names)
                    printTime += printTimeStep
                    
                if self.reac.T >= tempLimit:
                    ignitionTime = self.netw.time
                
                prevTime = curTime
                


class VolumeProfile(object):
    def __init__(self, self.keywords):
        self.time = np.array(self.keywords['vproTime'])
        self.volume = np.array(keywords['vproVol'])
        self.velocity = np.diff(self.volume)/np.diff(self.time)
        self.velocity = np.append(self.velocity,0)
    def __call__(self,t):
        if t == 0:
            return 0
        if t < self.time[1]:
            tim0 = self.time[0]
            tim1 = self.time[1]
            vel0 = self.velocity[0]
            vel1 = self.velocity[1]
        elif t >= self.time[1] and t <= self.time[-1]:
            tim0 = self.time[self.time < t][-1]
            tim1 = self.time[np.where(self.time == tim0)[0][0]+1]
            vel0 = self.velocity[self.time < t][-1]
            vel1 = self.velocity[np.where(self.time == tim0)[0][0]+1]
        elif t > self.time[-1]:
            return 0
        
        interp = vel0 + (vel1-vel0)*(t-tim0)/(tim1-tim0)
        return interp
        
class TemperatureProfile(object):
    def __init__(self,keywords):
        self.time = np.array(keywords['TproTime'])
        self.temperature = np.array(keywords['TproTemp'])
    def __call__(self,t):
        if t == 0:
            return self.temperature[0]
        if t < self.time[1]:
            tim0 = self.time[0]
            tim1 = self.time[1]
            temp0 = self.temperature[0]
            temp1 = self.temperature[1]
        elif t >= self.time[1] and t <= self.time[-1]:
            tim0 = self.time[self.time < t][-1]
            tim1 = self.time[np.where(self.time == tim0)[0][0]+1]
            temp0 = self.temperature[self.time < t][-1]
            temp1 = self.temperature[np.where(self.time == tim0)[0][0]+1]
        elif t > self.time[-1]:
            return self.temperature[-1]
        
        interp = temp0 + (temp1-temp0)*(t-tim0)/(tim1-tim0)
        return interp

