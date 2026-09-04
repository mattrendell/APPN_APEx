Path to this folder: I:\APPN 2026\2026_CalibrationTrial_I_SIF_DPIRD\2026York_F\GOBI\20260812

There are five flights. All the data were collected from DPIRD's Gobi sensor mounted on UWA's M350 drone. Data was collected by Franco. UWA's data on the other hand was collected by us. Along rows flights were attempted three times because of the GNSS error in UWA's Gobi sensor.

Note that YCD stands for York Calibration Dpird.

run00 --> YCD_Row1 --> First attempt on along rows direction. There was a small patch of cloud. So next flight was taken. Discard this flight.
run01 --> YCD_Row2 --> Second attempt on along rows direction.
run02 --> YCD_Row3 --> Third attempt on along rows direction. Somehow, the resolution of this data is 4x lower (6cm/px) --> this issue was solved by using run01's DSM when processing this run's data in GPT.
run03 --> YCD_Range2 --> Along ranges direction. The VNIR lens cap was not removed during data collection. Discard this flight.
run04 --> YCD_EW3 --> East-West direction.