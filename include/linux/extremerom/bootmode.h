/*
 * Copyright (c) 2025, The Linux Foundation. All rights reserved.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 and
 * only version 2 as published by the Free Software Foundation.
 */

#ifndef EXTREMEROM_BOOTMODE_H
#define EXTREMEROM_BOOTMODE_H

enum extremerom_bootmode {
	BOOTMODE_NORMAL,
	BOOTMODE_CHARGER,
	BOOTMODE_RECOVERY,
	BOOTMODE_UNKNOWN
};

enum extremerom_bootmode get_extremerom_bootmode(void);

#endif
