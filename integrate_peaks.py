"""

Integrate Peaks v.0.1.0. Build Date : : :.
Written by Edward Lau (edward.lau@me.com) 2016-2017


"""

import pandas as pd
import scipy.integrate
import tqdm
from multiprocessing import Pool, cpu_count

class Peaks(object):
    def __init__(self, msdata, rt_idx, mslvl_idx):
        """
        This class uses the parsed peaks from pymzml for peak recognition and counting

        :param msdata: The dictionary of spectrum ID vs. mz/I array from parse Mzml
        :param rt_idx: The retention time index dictionary from parse Mzml
        :param mslvl_idx: The spectrum MS level dictionary from parse Mzml
        """

        self.msdata = msdata
        self.rt_idx = rt_idx
        self.mslvl_idx = mslvl_idx
        self.id = pd.DataFrame()
        self.iso_to_do = []
        self.rt_tolerance = 30
        self.mass_tolerance = 100e-6
        self.njobs = 10
        self.intensity_over_time = []
        self.isotope_intensities = []

    def set_iso_to_do(self, iso_to_do):
        """
        Setter for isotope
        :param iso_to_do:
        :return:
        """

        self.iso_to_do = iso_to_do

    def set_rt_tolerance(self, rt_tolerance):
        """
        Setter for rt_tolerance

        :param rt_tolerance:
        :return:
        """

        self.rt_tolerance = rt_tolerance

    def set_mass_tolerance(self, mass_tolerance):
        """
        Setter for mass tolerance
        :param iso_to_do:
        :return:
        """

        self.mass_tolerance = mass_tolerance

    def associate_id(self, id_df):
        """
        Associate the mzid peptide identification file to this peak list

        :param id_df: Fraction-specific ID list from mzid or Percolator
        :return:
        """

        self.id = id_df

    def get_isotopes_from_amrt_multiwrapper(self, num_thread=1, chunk_size=50):

        """
        Multi-threaded wrapper to get the isotopomers from peptide accurate mass and retention time of all qualifying
        peptides at the same time. The chunk size of multithreading is set to 50 at the moment.

        :param num_thread: Number of threads (default to 1)
        :param chunk_size: Number of threads (default to 1)
        :return:
        """

        assert num_thread >= cpu_count()-1, "Number of threads exceeded CPU count"

        assert chunk_size > 0, "Chunk size must be a positive integer"

        loop_count = range(len(self.id))

        chunk_size = max(chunk_size, 250)

        with Pool(processes=num_thread) as p:
            result = list(tqdm.tqdm(p.imap(self.get_isotopes_from_amrt_wrapper,
                                           loop_count,
                                           chunksize=chunk_size),
                                    total=max(loop_count)))

        return result

    def get_isotopes_from_amrt_wrapper(self, index):
        """
        Wrapper for the get_isotope_from_scan_id() function below

        :param index: int The row number of the peptide ID table passed from the wrapper.
        :return: list [index, pep_id, m0, m1, m2, ...]

        """

        peptide_mass = float(self.id.loc[index, 'peptide mass'])

        scan_number = int(self.id.loc[index, 'scan'])

        charge = float(self.id.loc[index, 'charge'])

        self.intensity_over_time = self.get_isotopes_from_amrt(peptide_am=peptide_mass,
                                                               peptide_scan=scan_number,
                                                               z=charge)

        if not self.intensity_over_time:
            print('Empty intensity over time')

        result = [index] + [(self.id.loc[index, 'pep_id'])] + self.integrate_isotope_intensity()

        return result


    def get_isotopes_from_amrt(self, peptide_am, peptide_scan, z):
        """
        Given peptide accurate mass and retention time and charge, find all the isotopic peaks intensity at each
        scan within the retention time window

        :param peptide_am: float Accurate peptide mass
        :param peptide_scan: int Scan number
        :param z: int Peptide charge
        :return: List of intensity over time
        """

        # Proton mass from NIST
        proton = 1.007825

        # Get retention time from scan number
        peptide_rt = self.rt_idx.get(peptide_scan)

        # Calculate precursor mass from peptide monoisotopic mass
        peptide_prec = (peptide_am + (z * proton)) / z

        intensity_over_time = []

        # Choose the scan numbers from the index; one-line list comprehension?
        nearby_scans = [[i, rt] for i, rt in self.rt_idx.items()
                        if abs(rt - peptide_rt) <= self.rt_tolerance and self.mslvl_idx[i] == 1]

        # Loop through each spectrum, check if it is an MS1 spectrum, check if it is within 1 minute of retention time
        for nearbyScan_id, nearbyScan_rt in nearby_scans:
            # Get the spectrum based on the spectrum number

            for iso in self.iso_to_do:

                # Set upper and lower bound

                peptide_prec_iso_am = peptide_prec + (iso * proton / z)

                upper = peptide_prec_iso_am + (peptide_prec_iso_am * (self.mass_tolerance/2))

                lower = peptide_prec_iso_am - (peptide_prec_iso_am * (self.mass_tolerance/2))

                matching_int = sum([I for mz_value, I in self.msdata.get(nearbyScan_id) if upper > mz_value > lower])

                intensity_over_time.append([nearbyScan_rt, iso, matching_int, peptide_prec_isotopomer_am])

        return intensity_over_time

    def integrate_isotope_intensity(self):
        """
        Given a list of isotopomer intensity over time, give the integrated intensity of each isotopomer

        :return: Integrated intensity of each isotopomer
        """
        # Integrate the individual isotopomers
        iso_intensity = []

        for j in self.iso_to_do:

            isotopomer_profile = [[rt, I] for rt, iso, I, mz_value in self.intensity_over_time if iso == j]

            # If there is no isotopomer profile, set area to 0
            if isotopomer_profile:
                iso_df = pd.DataFrame(isotopomer_profile)
                iso_area = scipy.integrate.trapz(iso_df[1], iso_df[0])
                # Remove all negative areas
                iso_area = max(iso_area, 0)

            else:
                iso_area = 0

            iso_intensity.append(iso_area)

        return iso_intensity

    # def make_index(self):
    #     """
    #     Generate two indices:
    #     MS1 index: a dictionary of ms1 scan number vs. rt
    #     MS2 index: a dictionary of ms2 scan number vs. rt
    #     :return: True
    #     """
    #
    #     # Index retention time; turn this into a dictionary please.
    #     i = 0
    #     for spectrum in self.msdata:
    #         i += 1
    #
    #         # # Print progress every 1000 spectra
    #         try:
    #             if i % 1000 == 0:
    #                 print('Indexing ' + str(i) + ' of ' +
    #                       str(self.msdata.getSpectrumCount()) + ' spectra (ID: ' + str(spectrum['id']) + ').')
    #
    #         except:
    #             pass
    #
    #         # Only indexing MS1 and MS2 scans
    #         if spectrum['ms level'] == 1:
    #             self.ms1_index[spectrum['id']] = spectrum['MS:1000016']
    #         if spectrum['ms level'] == 2:
    #             self.ms2_index[spectrum['id']] = spectrum['MS:1000016']
    #
    #     return True


    # def get_rt_from_scan(self, peptide_scan):
    #     """
    #     For the deprecated integrate function
    #     Given the scan number, return the retention time
    #     :param peptide_scan: the peptide scan number
    #     :return: the retention time
    #     """
    #
    #     # Some spectral properties: 'id', 'ms level', 'total ion current'
    #     # NB: According to the mzml OBO, MS:1000016 is the retention time
    #     return self.msdata[peptide_scan]['MS:1000016']
    #
    #
    # def get_scans_to_do(self, peptide_scan, rt_tolerance):
    #     """
    #     For the new integrate_fast function
    #     Given the scan number, return all the scan IDs to integrate
    #     :param peptide_scan:    MS2 scan number
    #     :param rt_tolerance:    Retention time tolerance in min
    #     :return: the ID of the scans to be integrated
    #     """
    #
    #     peptide_rt = self.ms2_index[peptide_scan]
    #
    #     if self.ms2_index == {}:
    #         print('No index found: creating new index.')
    #         self.make_index()
    #
    #     # Choose the scan numbers from the index
    #     nearbyScans = []
    #     for scan_id, scan_rt in self.ms1_index.items():
    #         if abs(scan_rt - peptide_rt) <= rt_tolerance:
    #             nearbyScans.append([scan_id, scan_rt])
    #
    #     return nearbyScans
    #
    #
    # def get_isotope_from_scan_id(self, peptide_am, z, spectrum_id, iso_to_do):
    #     """
    #     For the new integrate_fast function, get isotope intensities of a scan
    #     given a peptide m/z and RT combination
    #     :param peptide_am:  Peptide accurate mass
    #     :param z:           Peptide charge
    #     :param spectrum_id: Scan number?
    #     :param iso_to_do:   List of isotopomers to integrate
    #     :return:
    #     """
    #
    #     timeDependentIntensities = []
    #
    #     # Get the spectrum based on the spectrum number
    #     try:
    #         spectrum = self.msdata[spectrum_id]
    #
    #     except KeyError:
    #
    #         print('[error] spectrum index out of bound')
    #         return []
    #
    #     # 2018-09-07 Need to catch a number of errors of XML tree not
    #     # Being able to read the spectrum object returned by pymzml
    #     except xml.etree.ElementTree.ParseError:
    #         """
    #         print('[warning] XML eTree does not appear to be able to read this spectrum',
    #                   '(scan number:', str(spectrum_id) + ')', sep=' ')
    #         """
    #         return []
    #
    #     assert spectrum['ms level'] == 1, '[error] specified spectrum is not a parent ion scan'
    #
    #     # Loop through every isotope in the to-do list
    #     for i in iso_to_do:
    #
    #         iso_mz = peptide_am + ((i * 1.003) / z)
    #
    #         matchList = spectrum.has_peak(iso_mz)
    #
    #         if matchList:
    #             for mz, I in matchList:
    #                 timeDependentIntensities.append([spectrum_id, i, I, mz])
    #         else:
    #             timeDependentIntensities.append([spectrum_id, i, 0, iso_mz])
    #
    #     return timeDependentIntensities