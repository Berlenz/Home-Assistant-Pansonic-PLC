"""MEWTOCOL transport implementation for Panasonic PLC communication."""

from __future__ import annotations

import logging
import socket
import struct
import threading
from enum import Enum, unique

from typing import Any

_LOGGER = logging.getLogger(__name__)


class Exception_InvalidAddress(Exception):
    """Raised when the PLC address is invalid."""


class Exception_InvalidValue(Exception):
    """Raised when a write payload is invalid."""


@unique
class DataTypes(str, Enum):
    """Supported data types for values exchanged with the PLC."""
    BOOL  = "BOOL"    #1bit binary value                R0, X0, Y0, L0, T0, C1000
    INT   = "INT"     #16bit signed integer value       DT0, FL0, WR0, WX0, WY0, WL0
    DINT  = "DINT"    #32bit signed integer value       DDT0, DFL0, DWR0, DWX0, DWY0, DWL0
    UINT  = "UINT"    #16bit unsigned integer value     DT0, FL0, WR0, WX0, WY0, WL0
    UDINT = "UDINT"   #32bit unsigned integer value     DDT0, DFL0, DWR0, DWX0, DWY0, DWL0
    WORD  = "WORD"    #16bit hex value                  DT0, FL0, WR0, WX0, WY0, WL0
    DWORD = "DWORD"   #32bit hex value                  DDT0, DFL0, DWR0, DWX0, DWY0, DWL0
    REAL  = "REAL"    #32bit float value                DDT0, DFL0, DWR0, DWX0, DWY0, DWL0


class MewtocolComConnection:
    """Thread-safe wrapper around the MEWTOCOL TCP connection."""

    def __init__(self, sIPV4Address: str, iPort: int, iStationNumber: int = 0) -> None:
        """Initialize the connection wrapper."""
        self._sIPV4Address = sIPV4Address
        self._iPort = iPort
        self._lock = threading.Lock()
        self._socket: socket.socket | None = None
        if 0 < iStationNumber <= 99:
            self._sStationNumber = f"{iStationNumber:02d}"
        else:
            self._sStationNumber = "EE"
            if iStationNumber != 0:
                raise Exception_InvalidValue(f"Invalid station number {iStationNumber} (valid 0..99)")

    def to_int(self, sValue: str) -> int:
        try:
            return int(sValue)
        except ValueError:
            return int(float(sValue))

    def to_unsigned_int(self, sValue: str) -> int:
        iValue = self.to_int(sValue)
        return max(iValue, 0)

    def Connect(self) -> None:
        """Open the TCP connection if it is not already open."""
        if self._socket is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5) #seconds
            self._socket.connect((self._sIPV4Address, self._iPort))
            _LOGGER.debug("Mewtocol: Connected to PLC %s:%s", self._sIPV4Address, self._iPort)

    def Close(self) -> None:
        """Close the TCP connection when the integration unloads."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None
            _LOGGER.debug("Mewtocol: Disconnected from PLC %s", self._sIPV4Address)

    def ReadPlcStatus(self) -> str | None:
        sMewtocolCommand = "%" + self._sStationNumber + "#RT"
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        if not self._VerifyResponseFromPlc(sResponseFromPlc, "RT"):
            return None
        return sResponseFromPlc[6 : len(sResponseFromPlc) - 3] # e.g. "%EE$RTxxxxxxzz\r" -> x = status data, zz = BCC

    def ReadFromPlc(self, sFPAddress: str, sDataType: str) -> str | None:
        sDataTypeUpper = sDataType.upper()
        if sDataTypeUpper == DataTypes.BOOL:
            return self.ReadFromPlc_BOOL(sFPAddress)
        if sDataTypeUpper in (DataTypes.INT, DataTypes.DINT):
            return self.ReadFromPlc_INT_DINT(sFPAddress)
        if sDataTypeUpper in (DataTypes.UINT, DataTypes.UDINT):
            return self.ReadFromPlc_UINT_UDINT(sFPAddress)
        if sDataTypeUpper == DataTypes.REAL:
            return self.ReadFromPlc_REAL(sFPAddress)
        if sDataTypeUpper in (DataTypes.WORD, DataTypes.DWORD):
            return self.ReadFromPlc_Hex(sFPAddress)
        raise TypeError(f"Invalid data type {sDataType}")

    def ReadFromPlcBatch(self, requests: list[tuple[str, str]]) -> dict[str, str | None]:
        """Read several register values in a single MEWTOCOL range read where possible."""
        results: dict[str, str | None] = {}

        pending_word_reads: list[tuple[str, str]] = []
        pending_bit_reads: list[tuple[str, str]] = []
        for sFPAddress, sDataType in requests:
            if self._CanBatchReadBitAddress(sFPAddress, sDataType):
                pending_bit_reads.append((sFPAddress, sDataType))
                continue
            if self._CanBatchReadWordAddress(sFPAddress, sDataType): #Word addresses like DT0, DDT0, WR0, ...
                pending_word_reads.append((sFPAddress, sDataType))
                continue

            results[sFPAddress] = self.ReadFromPlc(sFPAddress, sDataType)

        if pending_word_reads:
            results.update(self._ReadFromPlcBatchGroupWordAddresses(pending_word_reads)) #Word addresses like DT0, FL0, LD0, WL0, WX0, WY0, WR0
        if pending_bit_reads:
            results.update(self._ReadFromPlcBatchGroupBitAddresses(pending_bit_reads)) #Bit addresses like R0, X0, Y0, L0, T0, C1000

        return results

    def WriteToPlc(self, sFPAddress: str, sDataType: str, sValue: str) -> str | bool:
        sDataTypeUpper = sDataType.upper()
        if sDataTypeUpper == DataTypes.BOOL:
            return self.WriteToPlc_BOOL(sFPAddress, sValue)
        if sDataTypeUpper in (DataTypes.INT, DataTypes.DINT):
            return self.WriteToPlc_INT_DINT(sFPAddress, sValue)
        if sDataTypeUpper in (DataTypes.UINT, DataTypes.UDINT):
            return self.WriteToPlc_UINT_UDINT(sFPAddress, sValue)
        if sDataTypeUpper == DataTypes.REAL:
            return self.WriteToPlc_REAL(sFPAddress, sValue)
        if sDataTypeUpper in (DataTypes.WORD, DataTypes.DWORD):
            return self.WriteToPlc_Hex(sFPAddress, sValue)
        raise TypeError(f"Invalid data type {sDataType}")

    def ReadFromPlc_BOOL(self, sFPAddress: str) -> str | None:  #Read values as data type BOOL ("0" to "1")
        if not self._IsContactAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type BOOL") #Not allowed addresse: WR0, WX0, WY0, WL0, DWR0, DWX0, DWY0, DWL0, DT0, FL0, DDT0, DFL0
        return self._ReadFromPlc_SingleAddress(sFPAddress) #Allowed bit addresses: R0, X0, Y0, L0, T0, C1000

    def WriteToPlc_BOOL(self, sFPAddress: str, sValue: str) -> bool: #Write values as data type BOOL ("0" to "1")
        if not self._IsContactAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type BOOL") #Not allowed addresse: WR0, WX0, WY0, WL0, DWR0, DWX0, DWY0, DWL0, DT0, FL0, DDT0, DFL0
        return self._WriteToPlc_SingleAddress(sFPAddress, sValue) #Allowed bit addresses: R0, X0, Y0, L0, T0, C1000

    def ReadFromPlc_Hex(self, sFPAddress: str) -> str | None: #Read values as data type WORD ("0000" to "FFFF"), DWORD ("00000000" to "FFFFFFFF")
        if self._IsContactAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type WORD or DWORD") #Not allowed addresse: R0, X0, Y0, L0, T0, C1000
        return self._ReadFromPlc_SingleAddress(sFPAddress) #Allowed addresses 16bit: DT0, FL0, WR0, WX0, WY0, WL0 => WORD; 32bit: DDT0, DFL0, DWR0, DWX0, DWY0, DWL0 => DWORD

    def WriteToPlc_Hex(self, sFPAddress: str, sValue: str) -> bool: #Write values as data type WORD ("0000" to "FFFF"), DWORD ("00000000" to "FFFFFFFF")
        if self._IsContactAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type WORD or DWORD") #Not allowed addresse: R0, X0, Y0, L0, T0, C1000
        return self._WriteToPlc_SingleAddress(sFPAddress, sValue) #Allowed addresses 16bit: DT0, FL0, WR0, WX0, WY0, WL0 => WORD; 32bit: DDT0, DFL0, DWR0, DWX0, DWY0, DWL0 => DWORD

    def ReadFromPlc_INT_DINT(self, sFPAddress: str) -> str | None: #Read values as data type INT ("-32768" to "32767"), DINT ("-2147483648" to "2147483647")
        if self._IsContactAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type INT or DINT") #Not allowed addresse: R0, X0, Y0, L0, T0, C1000
        sHexValue = self._ReadFromPlc_SingleAddress(sFPAddress) #Allowed addresses 16bit: DT0, FL0, WR0, WX0, WY0, WL0 => INT; 32bit: DDT0, DFL0, DWR0, DWX0, DWY0, DWL0 => DINT
        if sHexValue is not None:
            return str(int.from_bytes(bytes.fromhex(sHexValue), byteorder="big", signed=True)) #hex to integer
        return None

    def WriteToPlc_INT_DINT(self, sFPAddress: str, sValue: str) -> bool: #Write values as data type INT ("-32768" to "32767"), DINT ("-2147483648" to "2147483647")
        if self._IsContactAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type INT or DINT") #Not allowed addresse: R0, X0, Y0, L0, T0, C1000
        iValue = self.to_int(sValue) #Allowed addresses 16bit: DT0, FL0, WR0, WX0, WY0, WL0 => INT; 32bit: DDT0, DFL0, DWR0, DWX0, DWY0, DWL0 => DINT
        return self._WriteToPlc_SingleAddress(sFPAddress, iValue.to_bytes(self._GetValueSizeInBytes(sFPAddress), byteorder="big", signed=True).hex())

    def ReadFromPlc_UINT_UDINT(self, sFPAddress: str) -> str | None: #Read values as data type UINT ("0" to "65535"), UDINT ("0" to "4294967295")
        if self._IsContactAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type UINT or UDINT") #Not allowed addresse: R0, X0, Y0, L0, T0, C1000
        sHexValue = self._ReadFromPlc_SingleAddress(sFPAddress) #Allowed addresses 16bit: DT0, FL0, WR0, WX0, WY0, WL0 => UINT; 32bit: DDT0, DFL0, DWR0, DWX0, DWY0, DWL0 => UDINT
        if sHexValue is not None:
            return str(int(sHexValue, 16))
        return None

    def WriteToPlc_UINT_UDINT(self, sFPAddress: str, sValue: str) -> bool: #Write values as data type UINT ("0" to "65535"), UDINT ("0" to "4294967295")
        if self._IsContactAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type UINT or UDINT") #Not allowed addresse: R0, X0, Y0, L0, T0, C1000
        iValue = self.to_unsigned_int(sValue) #Allowed addresses 16bit: DT0, FL0, WR0, WX0, WY0, WL0 => UINT; 32bit: DDT0, DFL0, DWR0, DWX0, DWY0, DWL0 => UDINT
        return self._WriteToPlc_SingleAddress(sFPAddress, iValue.to_bytes(self._GetValueSizeInBytes(sFPAddress), byteorder="big", signed=False).hex())

    def ReadFromPlc_REAL(self, sFPAddress: str) -> str | None: #Read values as data type REAL (e.g. "3.1415")
        if not self._Is32BitAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type REAL") #Not allowed addresse: 0, X0, Y0, L0, T0, C1000, WR0, WX0, WY0, WL0, DT0, FL0
        sHexValue = self._ReadFromPlc_SingleAddress(sFPAddress) #Allowed addresses: DDT0, DFL0, DWR0, DWX0, DWY0, DWL0
        if sHexValue is not None:
            return str(struct.unpack(">f", struct.pack(">I", int(sHexValue, 16)))[0]) #32 bit hex data into IEEE 754 floating point
        return None

    def WriteToPlc_REAL(self, sFPAddress: str, sValue: str) -> bool: #Write values as data type REAL (e.g. "3.1415")
        if not self._Is32BitAddress(sFPAddress):
            raise Exception_InvalidAddress(f"{sFPAddress} is invalid or not usable with the data type REAL") #Not allowed addresse: 0, X0, Y0, L0, T0, C1000, WR0, WX0, WY0, WL0, DT0, FL0
        return self._WriteToPlc_SingleAddress(sFPAddress, f"{struct.unpack('>I', struct.pack('>f', float(sValue)))[0]:X}")

    @staticmethod
    def _get_address_offset(sFPAddress: str) -> int:
        """Return the numeric offset for a PLC register address."""
        digits = "".join(ch for ch in sFPAddress if ch.isdigit()) #0..9
        return int(digits) if digits else 0

    def _CanBatchReadWordAddress(self, sFPAddress: str, sDataType: str) -> bool:
        sDataTypeUpper = sDataType.upper()
        if sDataTypeUpper in (DataTypes.INT, DataTypes.DINT, DataTypes.UINT, DataTypes.UDINT, DataTypes.REAL, DataTypes.WORD, DataTypes.DWORD):
            return self._GetWordAddressBatchReadInfo(sFPAddress) is not None
        return False

    def _CanBatchReadBitAddress(self, sFPAddress: str, sDataType: str) -> bool:
        sDataTypeUpper = sDataType.upper()
        return sDataTypeUpper == DataTypes.BOOL and self._GetBitAddressBatchReadInfo(sFPAddress) is not None

    def _GetWordAddressBatchReadInfo(self, sFPAddress: str) -> tuple[str, str] | None:
        if self._Is16BitRegisterAddress(sFPAddress):
            return ("RD", sFPAddress[0:1]) #MEWNET command code, memory area code: DT0 => "D", LD0 => "L", FL0 => "F"
        if self._Is32BitRegisterAddress(sFPAddress):
            return ("RD", sFPAddress[1:2]) #MEWNET command code, memory area code: DDT0 => "D", DLD0 => "L", DFL0 => "F"
        if self._Is16BitContactAddress(sFPAddress):
            return ("RC", sFPAddress[0:1]) #MEWNET command code, memory area code: WR0 => R, WX0 => X, WY0 => Y, WL0 => L
        if self._Is32BitContactAddress(sFPAddress):
            return ("RC", sFPAddress[1:2]) #MEWNET command code, memory area code: DWR0 => R, DWX0 => X, DWY0 => Y, DWL0 => L
        return None

    def _GetBitAddressBatchReadInfo(self, sFPAddress: str) -> tuple[str, str, str] | None:
        if not self._IsContactAddress(sFPAddress):
            return None
        if len(sFPAddress) > 5: #allowed bit address range: R0..R999F
            return None

        sArea = sFPAddress[0:1]
        sOffset = sFPAddress[1:].upper()
        if len(sOffset) == 0 or len(sOffset) > 4:
            return None
        sWordOffset = sOffset[:-1]
        sBitOffset = sOffset[-1:]
        if len(sWordOffset) > 0 and not sWordOffset.isdigit():
            return None
        if not self._is_hex(sBitOffset):
            return None

        return ("RC", sArea, sOffset)

    def _ReadFromPlcBatchGroupBitAddresses(self, requests: list[tuple[str, str]]) -> dict[str, str | None]:
        split_groups = self._BuildContactBitSplitGroups(requests)
        if not split_groups:
            return {}

        results: dict[str, str | None] = {}
        for grouped in split_groups:
            bit_values = self._ReadFromPlc_ContactBitRange([(item[2], item[3]) for item in grouped])
            if bit_values is None:
                for sFPAddress, _, _, _ in grouped:
                    results[sFPAddress] = None
                continue

            for bit_index, (sFPAddress, _, _, _) in enumerate(grouped):
                if bit_index < 0 or bit_index >= len(bit_values):
                    results[sFPAddress] = None
                else:
                    results[sFPAddress] = bit_values[bit_index]

        return results

    def _BuildContactBitSplitGroups(self, requests: list[tuple[str, str]]) -> list[list[tuple[str, str, str, str]]]:
        """Build RCP bit batches (up to 8 addresses, mixed memory areas allowed)."""
        grouped: list[tuple[str, str, str, str]] = []
        for sFPAddress, sDataType in requests:
            sDataTypeUpper = sDataType.upper()
            if sDataTypeUpper != DataTypes.BOOL:
                continue

            batch_info = self._GetBitAddressBatchReadInfo(sFPAddress) #MEWNET command code "RC", memory area code R, X, Y, L, T, C, address offset R10 = "10"
            if batch_info is None:
                continue
            grouped.append((sFPAddress, sDataTypeUpper, batch_info[1], batch_info[2]))

        if not grouped:
            return []

        split_groups: list[list[tuple[str, str, str, str]]] = []
        for index in range(0, len(grouped), 8):
            split_groups.append(grouped[index : index + 8])

        return split_groups

    def _ReadFromPlcBatchGroupWordAddresses(self, requests: list[tuple[str, str]]) -> dict[str, str | None]:
        """Only processes word addresses like DT0, FL0, LD0, WL0, WX0, WY0, WR0. Ignors bit addresses like R0, X0, Y0, L0, T0, C1000"""
        if not requests:
            return {}

        split_groups = self._BuildBatchSplitGroups(requests)
        if not split_groups:
            return {}

        results: dict[str, str | None] = {}
        for grouped in split_groups:
            command_code, area_code = grouped[0][3], grouped[0][4]
            start_offset = min(self._get_address_offset(sFPAddress) for sFPAddress, _, _, _, _ in grouped)
            end_offset = max(self._get_address_offset(sFPAddress) + value_words - 1 for sFPAddress, _, value_words, _, _ in grouped)

            response_data = self._ReadFromPlcRange(command_code, area_code, start_offset, end_offset)
            if response_data is None:
                for sFPAddress, _, _, _, _ in grouped:
                    results[sFPAddress] = None
                continue

            for sFPAddress, data_type_upper, value_words, _, _ in grouped:
                register_offset = self._get_address_offset(sFPAddress) - start_offset
                offset_bytes = register_offset * 4
                if value_words == 1:
                    raw_value = response_data[offset_bytes : offset_bytes + 4]
                else:
                    raw_value = response_data[offset_bytes : offset_bytes + 8]
                results[sFPAddress] = self._DecodeBatchValue(raw_value, data_type_upper)

        return results

    def _BuildBatchSplitGroups(self, requests: list[tuple[str, str]]) -> list[list[tuple[str, str, int, str, str]]]:
        """Prepare deterministic batch groups split by command/area and max block size (25 words)."""
        if not requests:
            return []

        grouped: list[tuple[str, str, int, str, str]] = []
        for sFPAddress, sDataType in requests:
            sDataTypeUpper = sDataType.upper()
            if sDataTypeUpper in (DataTypes.INT, DataTypes.UINT, DataTypes.WORD):
                value_words = 1
            elif sDataTypeUpper in (DataTypes.DINT, DataTypes.UDINT, DataTypes.REAL, DataTypes.DWORD):
                value_words = 2
            else:
                continue

            batch_info = self._GetWordAddressBatchReadInfo(sFPAddress) #MEWNET command code "RD", "RC", memory area code "D", "R", "X", "Y", ...
            if batch_info is None:
                continue

            grouped.append((sFPAddress, sDataTypeUpper, value_words, batch_info[0], batch_info[1]))

        if not grouped:
            return []

        # Batch processing must be deterministic so mixed requests are grouped by
        # command code, memory area, and ascending register/contact offset.
        command_order = {"RD": 0, "RC": 1}
        area_order = {"D": 0, "F": 1, "L": 2, "R": 3, "X": 4, "Y": 5}
        grouped.sort(
            key=lambda item: (
                command_order.get(item[3], 99),
                area_order.get(item[4], 99),
                self._get_address_offset(item[0]),
            )
        )

        split_groups: list[list[tuple[str, str, int, str, str]]] = []
        current_group: list[tuple[str, str, int, str, str]] = []
        current_start: int | None = None
        current_end: int | None = None
        current_batch_key: tuple[str, str] | None = None

        for sFPAddress, data_type_upper, value_words, command_code, area_code in grouped:
            start_offset = self._get_address_offset(sFPAddress)
            end_offset = start_offset + value_words - 1
            batch_key = (command_code, area_code)
            if current_group and current_start is not None and current_end is not None and current_batch_key is not None:
                if batch_key != current_batch_key or (end_offset - current_start + 1) > 25:
                    split_groups.append(current_group)
                    current_group = []
                    current_start = None
                    current_end = None
                    current_batch_key = None
            if not current_group:
                current_group = [(sFPAddress, data_type_upper, value_words, command_code, area_code)]
                current_start = start_offset
                current_end = end_offset
                current_batch_key = batch_key
            else:
                current_group.append((sFPAddress, data_type_upper, value_words, command_code, area_code))
                current_end = max(current_end, end_offset)

        if current_group:
            split_groups.append(current_group)

        return split_groups

    def _ReadFromPlcRange(self, sCommandCode: str, sAreaCode: str, iStartAddressOffset: int, iEndAddressOffset: int) -> str | None:
        if sCommandCode == "RD":
            return self._ReadFromPlc_DataAreaRange(sAreaCode, iStartAddressOffset, iEndAddressOffset)
        if sCommandCode == "RC":
            return self._ReadFromPlc_ContactWordRange(sAreaCode, iStartAddressOffset, iEndAddressOffset)
        return None

    def _ReadFromPlc_DataAreaRange(self, sAreaCode: str, iStartAddressOffset: int, iEndAddressOffset: int) -> str | None:
        sStartAddressOffset = f"{iStartAddressOffset:05d}"
        sEndAddressOffset = f"{iEndAddressOffset:05d}"
        sMewtocolCommand = "%" + self._sStationNumber + "#RD" + sAreaCode + sStartAddressOffset + sEndAddressOffset
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        return self._DecodeResponseFromPlc_ReadData(sResponseFromPlc, "RD")

    def _ReadFromPlc_ContactWordRange(self, sAreaCode: str, iStartAddressOffset: int, iEndAddressOffset: int) -> str | None:
        sStartAddressOffset = f"{iStartAddressOffset:04d}"
        sEndAddressOffset = f"{iEndAddressOffset:04d}"
        sMewtocolCommand = "%" + self._sStationNumber + "#RCC" + sAreaCode + sStartAddressOffset + sEndAddressOffset
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        return self._DecodeResponseFromPlc_ReadData(sResponseFromPlc, "RC")

    def _ReadFromPlc_ContactBitRange(self, bit_requests: list[tuple[str, str]]) -> str | None:
        if not bit_requests:
            return None

        payload = "".join(f"{area_code}{sOffset.zfill(4)}" for area_code, sOffset in bit_requests)
        sMewtocolCommand = "%" + self._sStationNumber + "#RCP" + f"{len(bit_requests)}" + payload
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        return self._DecodeResponseFromPlc_ReadContactPlural(sResponseFromPlc, "RC", len(bit_requests))

    def _DecodeBatchValue(self, sHexValue: str, sDataType: str) -> str | None:
        if sDataType in (DataTypes.INT, DataTypes.DINT):
            return str(int.from_bytes(bytes.fromhex(sHexValue), byteorder="big", signed=True))
        if sDataType in (DataTypes.UINT, DataTypes.UDINT):
            return str(int(sHexValue, 16))
        if sDataType == DataTypes.REAL:
            return str(struct.unpack(">f", struct.pack(">I", int(sHexValue, 16)))[0])
        if sDataType == DataTypes.WORD:
            return sHexValue
        if sDataType == DataTypes.DWORD:
            return sHexValue
        return None

    def _ReadFromPlc_SingleAddress(self, sFPAddress: str) -> str | None: #Returns the read value or, if an error has occurred, the value None
        #_LOGGER.debug("MewtocolComConnection read (hub %s, IP %s:%i) FP address: %s", self._sPlcName, self._sIPV4Address, self._iPort, sFPAddress)
        if self._IsContactAddress(sFPAddress):  #R0, X0, Y0, L0, T0, C1000
            return self._ReadFromPlc_Contact(sFPAddress)
        if self._Is16BitContactAddress(sFPAddress): #WR0, WX0, WY0, WL0
            return self._ReadFromPlc_ContactWord(sFPAddress, 1) #Read 1 word (16bit)
        if self._Is32BitContactAddress(sFPAddress): #DWR0, DWX0, DWY0, DWL0
            return self._ReadFromPlc_ContactWord(sFPAddress[1:], 2) #cut "D" e.g. "DWX0" -> "WX0"; #Read 2 words (32bit)
        if self._Is16BitRegisterAddress(sFPAddress):  #DT0, FL0
            return self._ReadFromPlc_DataArea(sFPAddress, 1) #Read 1 word (16bit)
        if self._Is32BitRegisterAddress(sFPAddress): #DDT0, DFL0
            return self._ReadFromPlc_DataArea(sFPAddress[1:], 2) #cut "D" e.g. "DDT0" -> "DT0"; #Read 2 words (32bit)
        raise Exception_InvalidAddress(f"Invalid address {sFPAddress}") #Error unknown address, should not happen because _ReadFromPlc_SingleAddress() should be called only for valid addresses

    def _WriteToPlc_SingleAddress(self, sFPAddress: str, sHexValue: str) -> bool: #Returns the read value or, if an error has occurred, the value None
        if len(sHexValue) == 0:
            raise Exception_InvalidValue(f"Invalid value {sHexValue}")
        sHexValue = sHexValue.upper()
        #_LOGGER.debug("MewtocolComConnection write (hub %s, IP %s:%i) FP address: %s", self._sPlcName, self._sIPV4Address, self._iPort, sFPAddress)
        if self._IsContactAddress(sFPAddress): #R0, X0, Y0, L0, T0, C1000
            return self._WriteToPlc_Contact(sFPAddress, sHexValue)
        if self._Is16BitContactAddress(sFPAddress): #WR0, WX0, WY0, WL0
            if len(sHexValue) > 4 or not self._is_hex(sHexValue):
                raise Exception_InvalidValue(f"Invalid value {sHexValue}")
            return self._WriteToPlc_ContactWord(sFPAddress, 1, sHexValue) #Write 1 word (16bit)
        if self._Is32BitContactAddress(sFPAddress): #DWR0, DWX0, DWY0, DWL0
            if len(sHexValue) > 8 or not self._is_hex(sHexValue):
                raise Exception_InvalidValue(f"Invalid value {sHexValue}")
            return self._WriteToPlc_ContactWord(sFPAddress[1:], 2, sHexValue) #cut "D" e.g. "DWX0" -> "WX0"; #Write 2 words (32bit)
        if self._Is16BitRegisterAddress(sFPAddress): #DT0, FL0
            if len(sHexValue) > 4 or not self._is_hex(sHexValue):
                raise Exception_InvalidValue(f"Invalid value {sHexValue}")
            return self._WriteToPlc_DataArea(sFPAddress, 1, sHexValue) #Write 1 word (16bit)
        if self._Is32BitRegisterAddress(sFPAddress): #DDT0, DFL0
            if len(sHexValue) > 8 or not self._is_hex(sHexValue):
                raise Exception_InvalidValue(f"Invalid value {sHexValue}")
            return self._WriteToPlc_DataArea(sFPAddress[1:], 2, sHexValue) #cut "D" e.g. "DDT0" -> "DT0"; #Write 2 words (32bit)
        raise Exception_InvalidAddress(f"Invalid address {sFPAddress}")

    def _IsContactAddress(self, sFPAddress: str) -> bool:
        sArea = sFPAddress[0:1]
        return sArea in {"R", "L", "X", "Y", "T", "C"}

    def _Is16BitContactAddress(self, sFPAddress: str) -> bool:
        sArea = sFPAddress[0:2]
        return sArea in {"WR", "WX", "WY", "WL"}

    def _Is32BitContactAddress(self, sFPAddress: str) -> bool:
        sArea = sFPAddress[0:3]
        return sArea in {"DWR", "DWX", "DWY", "DWL"}

    def _Is16BitOr32BitContactAddress(self, sFPAddress: str) -> bool:
        return self._Is16BitContactAddress(sFPAddress) or self._Is32BitContactAddress(sFPAddress)

    def _Is16BitRegisterAddress(self, sFPAddress: str) -> bool:
        sArea = sFPAddress[0:2]
        return sArea in {"DT", "LD", "FL"}

    def _Is32BitRegisterAddress(self, sFPAddress: str) -> bool:
        sArea = sFPAddress[0:3]
        return sArea in {"DDT", "DLD", "DFL"}

    def _Is16BitAddress(self, sFPAddress: str) -> bool:
        return self._Is16BitRegisterAddress(sFPAddress) or self._Is16BitContactAddress(sFPAddress)

    def _Is32BitAddress(self, sFPAddress: str) -> bool:
        return self._Is32BitRegisterAddress(sFPAddress) or self._Is32BitContactAddress(sFPAddress)

    def _GetValueSizeInBytes(self, sFPAddress: str) -> int:
        if self._Is16BitAddress(sFPAddress):
            return 2
        if self._Is32BitAddress(sFPAddress):
            return 4
        return 0

    def _CalculateBCC(self, sText: str) -> str:
        iBlockCheckCode = 0
        for ch in sText:
            iBlockCheckCode ^= ord(ch) #exclusive OR
        return f"{iBlockCheckCode:02X}" #Return hex value as two digit upper case string

    def _SendMewtocolCommandToPlc(self, sMewtocolCommand: str) -> str:
        with self._lock:
            try:
                self.Connect()
                assert self._socket is not None
                self._socket.sendall(sMewtocolCommand.encode("ascii"))
                return self._socket.recv(1024).decode("ascii")
            except Exception:
                self.Close()
                raise

    def _ReadFromPlc_DataArea(self, sFPAddress: str, iWordCount: int) -> str | None: # Read from DT, LD, FL addresses
        if len(sFPAddress) > 7: #e.g. allowed: DT0 .. DT99999
            raise Exception_InvalidAddress(f"Invalid address {sFPAddress}")
        iStartAddressOffset = int(sFPAddress[2:]) #e.g. "DT99" -> "99"
        sStartAddressOffset = f"{iStartAddressOffset:05d}"
        sEndAddressOffset = f"{(iStartAddressOffset + iWordCount - 1):05d}"
        sMewtocolCommand = "%" + self._sStationNumber + "#RD" + sFPAddress[0:1] + sStartAddressOffset + sEndAddressOffset
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        return self._DecodeResponseFromPlc_ReadData(sResponseFromPlc, "RD") #Returns the read value or, if an error has occurred, the value None

    def _WriteToPlc_DataArea(self, sFPAddress: str, iWordCount: int, sHexValue: str) -> bool: # Write to DT, LD, FL addresses
        if len(sFPAddress) > 7: #e.g. allowed: DT0 .. DT99999
            raise Exception_InvalidAddress(f"Invalid address {sFPAddress}")
        iStartAddressOffset = int(sFPAddress[2:]) #e.g. "DT99" -> "99"
        sStartAddressOffset = f"{iStartAddressOffset:05d}" #"99" -> "00099"
        sEndAddressOffset = f"{(iStartAddressOffset + iWordCount - 1):05d}"
        sMewtocolCommand = "%" + self._sStationNumber + "#WD" + sFPAddress[0:1] + sStartAddressOffset + sEndAddressOffset + self._SwapNibbles(sHexValue.rjust(iWordCount * 4, "0")) #%EE#WCCR00010002ABCDEF01zz\r
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        return self._VerifyResponseFromPlc(sResponseFromPlc, "WD")

    def _DecodeResponseFromPlc_ReadData(self, sResponseFromPlc: str, sCommandCode: str) -> str | None:
        if not self._VerifyResponseFromPlc(sResponseFromPlc, sCommandCode):
            return None
        if len(sResponseFromPlc) < 13: # should be "%EE$RDxxxxzz\r" or  "%EE$RDxxxx....yyyyzz\r"
            return None
        #Read only the data (last 3 bytes are CRC and cr)
        return self._SwapNibbles(sResponseFromPlc[6 : len(sResponseFromPlc) - 3]) # e.g. "%EE$RDxxxxyyyyzz\r" -> xxxx = first register value, yyyy = last register value, zz = BCC

    def _ReadFromPlc_Contact(self, sFPAddress: str) -> str | None: # commands: RCS read one contact; RCP read multiple contacts; RCC read contact word area
        # Read from R, L, X, Y, T, C addresses
        if len(sFPAddress) > 5: #e.g. allowed address range: R0 .. R999F
            raise Exception_InvalidAddress(f"Invalid address {sFPAddress}")
        sAddressOffset = sFPAddress[1:].zfill(4) #"99" -> "0099"
        sMewtocolCommand = "%" + self._sStationNumber + "#RCS" + sFPAddress[0:1] + sAddressOffset #Read Contact Single Bit: #%EE#RCSR001A (R1A)
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        return self._DecodeResponseFromPlc_ReadContact(sResponseFromPlc, "RC") #Returns the read value or, if an error has occurred, the value None

    def _WriteToPlc_Contact(self, sFPAddress: str, sValue: str) -> bool: # commands: WCS write one contact; RCP read multiple contacts; RCC read contact word area
        # Write to R, L, X, Y, T, C addresses
        if len(sFPAddress) > 5: #e.g. allowed address range: R0 .. R999F
            raise Exception_InvalidAddress(f"Invalid address {sFPAddress}")
        if sValue not in {"0", "1"}:
            raise Exception_InvalidValue(f"Invalid value {sValue}")
        sAddressOffset = sFPAddress[1:].zfill(4) #"99" -> "0099"
        sMewtocolCommand = "%" + self._sStationNumber + "#WCS" + sFPAddress[0:1] + sAddressOffset + sValue #Write Contact Single
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        return self._VerifyResponseFromPlc(sResponseFromPlc, "WC")

    def _DecodeResponseFromPlc_ReadContact(self, sResponseFromPlc: str, sCommandCode: str) -> str | None:
        if not self._VerifyResponseFromPlc(sResponseFromPlc, sCommandCode):
            return None
        if len(sResponseFromPlc) != 10: # should be "%EE$RCxzz\r"
            return None
        #Read only the data (last 3 bytes are BCC and CR)
        return sResponseFromPlc[6 : len(sResponseFromPlc) - 3]# e.g. "%EE$RCxzz\r" -> x = '0'/'1' contact value, zz = BCC

    def _DecodeResponseFromPlc_ReadContactPlural(self, sResponseFromPlc: str, sCommandCode: str, iExpectedBitCount: int) -> str | None:
        if not self._VerifyResponseFromPlc(sResponseFromPlc, sCommandCode):
            return None
        if len(sResponseFromPlc) < 9:
            return None

        sPayload = sResponseFromPlc[6 : len(sResponseFromPlc) - 3]
        if len(sPayload) != iExpectedBitCount:
            return None
        if any(ch not in {"0", "1"} for ch in sPayload):
            return None
        return sPayload

    def _ReadFromPlc_ContactWord(self, sFPAddress: str, iWordCount: int) -> str | None: # commands: RCS read one contact; RCP read multiple contacts; RCC read contact word area
        # Read WR, WX, WY, WL addresses
        if len(sFPAddress) > 6: #e.g. allowed: WR0 .. WR9999
            raise Exception_InvalidAddress(f"Invalid address {sFPAddress}")
        sStartAddressOffset = f"{int(sFPAddress[2:]):04d}" #e.g. "WR99" -> "99"
        sEndAddressOffset = f"{(int(sStartAddressOffset) + iWordCount - 1):04d}"
        sMewtocolCommand = "%" + self._sStationNumber + "#RCC" + sFPAddress[1:2] + sStartAddressOffset + sEndAddressOffset #Read contact word area: %EE#RCCR00010010 (WR1 to WR10)
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        return self._DecodeResponseFromPlc_ReadData(sResponseFromPlc, "RC")

    def _WriteToPlc_ContactWord(self, sFPAddress: str, iWordCount: int, sHexValue: str) -> bool: # commands: RCS read one contact; RCP read multiple contacts; RCC read contact word area
        # Write WR, WX, WY, WL addresses
        if len(sFPAddress) > 6: #e.g. allowed: WR0 .. WR9999
            raise Exception_InvalidAddress(f"Invalid address {sFPAddress}")
        sStartAddressOffset = f"{int(sFPAddress[2:]):04d}"#e.g. "WR99" -> "99"
        sEndAddressOffset = f"{(int(sStartAddressOffset) + iWordCount - 1):04d}"
        sMewtocolCommand = "%" + self._sStationNumber + "#WCC" + sFPAddress[1:2] + sStartAddressOffset + sEndAddressOffset + self._SwapNibbles(sHexValue.rjust(iWordCount * 4, "0")) #%EE#WCCR00010002ABCDEF01zz\r
        sMewtocolCommand += self._CalculateBCC(sMewtocolCommand)
        sMewtocolCommand += "\r"
        sResponseFromPlc = self._SendMewtocolCommandToPlc(sMewtocolCommand)
        return self._VerifyResponseFromPlc(sResponseFromPlc, "WC")

    def _VerifyResponseFromPlc(self, sResponseFromPlc: str, sCommandCode: str) -> bool:
        if len(sResponseFromPlc) < 9: # %EE!41zz\r; zz = BCC; => error code has at leased 9 characters
            return False # invalid response data
        if sResponseFromPlc[-1] != "\r":
            return False
        if sResponseFromPlc[-3:-1] != self._CalculateBCC(sResponseFromPlc[:-3]): #%EE!41xx\r => %EE!41
            return False # Wrong block check code
        if sResponseFromPlc[1:3] != self._sStationNumber:
            return False # e.g. "%EE$aa...\r" -> aa = command code
        if sResponseFromPlc[3] != "$":
            return False # e.g. "%EE!xxzz\r" -> xx = error code, zz = BCC
        if sResponseFromPlc[4:6] != sCommandCode:
            return False # e.g. "%EE$aa...\r" -> aa = command code
        return True

    def _SwapNibbles(self, sHexValue: str) -> str | None:
        #Values must be in blocks of 4 nipples (4x4 bits)
        MEWTOCOL_WORD_NIPPLE_SIZE = 4
        if len(sHexValue) % MEWTOCOL_WORD_NIPPLE_SIZE > 0:  # 4 characters = 1 word
            return None # error
        sHexValueSwapped = ""
        while len(sHexValue) >= MEWTOCOL_WORD_NIPPLE_SIZE:
            sTemp = sHexValue[0:MEWTOCOL_WORD_NIPPLE_SIZE]
            #Change back the low and high bytes
            sHexValueSwapped = sTemp[2:4] + sTemp[0:2] + sHexValueSwapped
            sHexValue = sHexValue[MEWTOCOL_WORD_NIPPLE_SIZE:]
        return sHexValueSwapped

    def _is_hex(self, sHexValue: str) -> bool: #Validates hex value, possible digits: 0123456789ABCDEF
        try:
            int(sHexValue, 16)
            return True
        except ValueError:
            return False