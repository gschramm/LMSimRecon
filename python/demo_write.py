from __future__ import annotations

import parallelproj
import utils
import array_api_compat.numpy as np
import matplotlib.pyplot as plt
from array_api_compat import to_device
from io_yardl import write_yardl

# device variable (cpu or cuda) that determines whether calculations
# are performed on the cpu or cuda gpu

dev = "cpu"
expected_num_trues = 1e6
num_iter = 2
num_subsets = 20
np.random.seed(42)

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# --- setup the scanner / LOR geometry ---------------------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------

# setup a line of response descriptor that describes the LOR start / endpoints of
# a "narrow" clinical PET scanner with 9 rings
lor_descriptor = utils.DemoPETScannerLORDescriptor(
    np, dev, num_rings=4, radial_trim=141
)

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# --- setup a simple 3D test image -------------------------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------

# image properties
voxel_size = (2.66, 2.66, 2.66)
num_trans = 128
num_ax = 2 * lor_descriptor.scanner.num_modules

# setup a box like test image
img_shape = (num_trans, num_trans, num_ax)
n0, n1, n2 = img_shape

# setup an image containing a box

img = np.tile(np.load("../data/SL.npy")[..., None], (1, 1, num_ax)).astype(np.float32)
img[:, :, :2] = 0
img[:, :, -2:] = 0

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# --- setup a non-TOF projector and project ----------------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------

res_model = parallelproj.GaussianFilterOperator(
    img_shape, sigma=4.5 / (2.355 * np.asarray(voxel_size))
)
projector = utils.RegularPolygonPETProjector(
    lor_descriptor, img_shape, voxel_size, resolution_model=res_model
)
projector.tof = False  # set this to True to get a time of flight projector

# forward project the image
noise_free_sinogram = projector(img)

# rescale the forward projection and image such that we get the expected number of trues
scale = expected_num_trues / np.sum(noise_free_sinogram)
noise_free_sinogram *= scale
img *= scale

# calculate the sensitivity image
sens_img = projector.adjoint(
    np.ones(noise_free_sinogram.shape, device=dev, dtype=np.float32)
)

# get the two dimensional indices of all sinogram bins
start_mods, end_mods, start_inds, end_inds = lor_descriptor.get_lor_indices()

# generate two sinograms that contain the linearized detector start and end indices
sino_det_start_index = (
    lor_descriptor.scanner.num_lor_endpoints_per_module[0] * start_mods + start_inds
)
sino_det_end_index = (
    lor_descriptor.scanner.num_lor_endpoints_per_module[0] * end_mods + end_inds
)

# add poisson noise to the noise free sinogram
noisy_sinogram = np.random.poisson(noise_free_sinogram)

# ravel the noisy sinogram and the detector start and end "index" sinograms
noisy_sinogram = noisy_sinogram.ravel()
sino_det_start_index = sino_det_start_index.ravel()
sino_det_end_index = sino_det_end_index.ravel()

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# --- convert the index sinograms in to listmode data ------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------

# generate listmode data from the noisy sinogram
event_sino_inds = np.repeat(np.arange(noisy_sinogram.shape[0]), noisy_sinogram)
# shuffle the event sinogram indices
np.random.shuffle(event_sino_inds)

event_det_id_1 = sino_det_start_index[event_sino_inds]
event_det_id_2 = sino_det_end_index[event_sino_inds]

print(f"number of events: {event_det_id_1.shape[0]}")

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# ---- convert LM detector ID arrays into PRD here ---------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------

# get a lookup table that contains the world coordinates of all scanner detectors
# this is a 2D array of shape (num_detectors, 3)
scanner_lut = lor_descriptor.scanner.all_lor_endpoints

# write the data to PETSIRD
write_yardl(event_det_id_1, event_det_id_2, scanner_lut, output_file="write_test.prd")

# HACK: write the sensitivity image to file
np.save("sensitivity_image.npy", sens_img)

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

vmax = 1.2 * img.max()
fig2, ax2 = plt.subplots(1, img.shape[2], figsize=(img.shape[2] * 2, 2))
for i in range(img.shape[2]):
    ax2[i].imshow(
        np.asarray(to_device(img[:, :, i], "cpu")), vmin=0, vmax=vmax, cmap="Greys"
    )
    ax2[i].set_title(f"ground truth sl {i+1}", fontsize="small")

fig2.tight_layout()
fig2.savefig("simulated_phantom.png")
