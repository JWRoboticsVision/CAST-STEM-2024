import argparse

from _init_paths import *
from lib.Utils import *
from lib.HandDetector import HandDetector
from lib.SequenceLoader import SequenceLoader


MP_CONFIG = {
    "max_num_hands": 2,
    "min_hand_detection_confidence": 0.1,
    "min_tracking_confidence": 0.5,
    "min_hand_presence_confidence": 0.5,
    "running_mode": "video",
    "frame_rate": 30,
    "device": "cuda" if torch.cuda.is_available() else "cpu",
}


def runner_draw_handmarks_results(rgb_images, handmarks, serials):
    vis_image = display_images(
        images=[
            draw_debug_image(
                rgb_image,
                hand_marks=handmarks[idx],
                draw_boxes=True,
                draw_hand_sides=True,
            )
            for idx, rgb_image in enumerate(rgb_images)
        ],
        names=serials,
        return_array=True,
    )
    return vis_image


def runner_mp_hand_detector(rgb_images, mp_config):
    detector = HandDetector(mp_config)
    marks_result = np.full((len(rgb_images), 2, 21, 2), -1, dtype=np.int64)
    for frame_id in range(len(rgb_images)):
        hand_marks, hand_sides, hand_scores = detector.detect_one(rgb_images[frame_id])

        if hand_sides:
            # update hand sides if there are two same hand sides
            if len(hand_sides) == 2 and hand_sides[0] == hand_sides[1]:
                if hand_scores[0] >= hand_scores[1]:
                    hand_sides[1] = "right" if hand_sides[0] == "left" else "left"
                else:
                    hand_sides[0] = "right" if hand_sides[1] == "left" else "left"
            # update hand marks result
            for i, hand_side in enumerate(hand_sides):
                if hand_side == "right":
                    marks_result[frame_id][0] = hand_marks[i]
                if hand_side == "left":
                    marks_result[frame_id][1] = hand_marks[i]

    marks_result = marks_result.astype(np.int64)

    return marks_result


def main():
    device = MP_CONFIG["device"]
    logger = get_logger(log_level="DEBUG", log_name="HandDetector")

    loader = SequenceLoader(sequence_folder, device=device)
    serials = loader.serials
    num_frames = loader.num_frames
    mano_sides = loader.mano_sides
    MP_CONFIG["max_num_hands"] = len(mano_sides)

    logger.info(">>>>>>>>>> Running MediaPipe Hand Detection <<<<<<<<<<")

    logger.debug(
        f"""Config Settings:
    - Device: {device}
    - Serials: {serials}
    - Number of Frames: {num_frames}
    - Mano Sides: {mano_sides}"""
    )

    mp_handmarks = {serial: None for serial in serials}
    tqbar = tqdm(total=len(serials), ncols=60, colour="green")
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(
                runner_mp_hand_detector,
                rgb_images=[
                    loader.get_rgb_image(f_id, serial) for f_id in range(num_frames)
                ],
                mp_config=MP_CONFIG,
            ): serial
            for serial in serials
        }

        for future in concurrent.futures.as_completed(futures):
            mp_handmarks[futures[future]] = future.result()
            tqbar.update()
            tqbar.refresh()

        del futures
    tqbar.close()

    logger.info("*** Updating Hand Detection Results with 'mano_sides' ***")
    if mano_sides is not None and len(mano_sides) == 1:
        for serial in serials:
            for frame_id in range(num_frames):
                if "right" in mano_sides:
                    if np.any(mp_handmarks[serial][frame_id][0] == -1) and np.all(
                        mp_handmarks[serial][frame_id][1] != -1
                    ):
                        mp_handmarks[serial][frame_id][0] = mp_handmarks[serial][
                            frame_id
                        ][1]
                    mp_handmarks[serial][frame_id][1] = -1
                if "left" in mano_sides:
                    if np.any(mp_handmarks[serial][frame_id][1] == -1) and np.all(
                        mp_handmarks[serial][frame_id][0] != -1
                    ):
                        mp_handmarks[serial][frame_id][1] = mp_handmarks[serial][
                            frame_id
                        ][0]
                    mp_handmarks[serial][frame_id][0] = -1

    # logger.info("*** Saving Hand Detection Results ***")
    # for serial in serials:
    #     tqdm.write(f"  - Saving hand detection results for {serial}")

    #     # Make folder to save hand detection results
    #     save_folder = sequence_folder / "processed" / "hand_detection" / serial
    #     make_clean_folder(save_folder)

    #     # Save hand detection results
    #     tqdm.write("    ** Saving Handmarks...")
    #     tqbar = tqdm(total=num_frames, ncols=60, colour="green")
    #     with concurrent.futures.ThreadPoolExecutor() as executor:
    #         futures = {
    #             executor.submit(
    #                 np.save,
    #                 save_folder / f"handmarks_{frame_id:06d}.npy",
    #                 mp_handmarks[serial][frame_id],
    #             ): frame_id
    #             for frame_id in range(num_frames)
    #         }
    #         for future in concurrent.futures.as_completed(futures):
    #             future.result()
    #             tqbar.update()
    #             tqbar.refresh()
    #         del futures
    #     tqbar.close()

    #     tqdm.write(f"    ** Generating vis images...")
    #     tqbar = tqdm(total=num_frames, ncols=60, colour="green")
    #     vis_images = [None] * num_frames
    #     with concurrent.futures.ThreadPoolExecutor() as executor:
    #         futures = {
    #             executor.submit(
    #                 draw_debug_image,
    #                 loader.get_rgb_image(frame_id, serial),
    #                 hand_marks=mp_handmarks[serial][frame_id],
    #                 draw_boxes=True,
    #                 draw_hand_sides=True,
    #             ): frame_id
    #             for frame_id in range(num_frames)
    #         }
    #         for future in concurrent.futures.as_completed(futures):
    #             vis_images[futures[future]] = future.result()
    #             tqbar.update()
    #             tqbar.refresh()
    #         del futures
    #     tqbar.close()

    #     tqdm.write(f"    ** Saving vis images...")
    #     tqbar = tqdm(total=num_frames, ncols=60, colour="green")
    #     with concurrent.futures.ThreadPoolExecutor() as executor:
    #         futures = {
    #             executor.submit(
    #                 write_rgb_image,
    #                 save_folder / f"vis_{frame_id:06d}.png",
    #                 vis_images[frame_id],
    #             ): frame_id
    #             for frame_id in range(num_frames)
    #         }
    #         for future in concurrent.futures.as_completed(futures):
    #             future.result()
    #             tqbar.update()
    #             tqbar.refresh()
    #         del futures
    #     tqbar.close()

    logger.info("*** Saving Hand Detection Results ***")
    save_folder = sequence_folder / "processed" / "hand_detection"
    save_folder.mkdir(parents=True, exist_ok=True)
    # swap axis to (2, num_frames, 21, 2)
    for serial in serials:
        mp_handmarks[serial] = np.swapaxes(mp_handmarks[serial], 0, 1).astype(np.int64)
    np.savez_compressed(save_folder / "mp_handmarks_results.npz", **mp_handmarks)

    logger.info("*** Generating Hand Detection Visualizations ***")
    tqdm.write("  - Generating vis images...")
    tqbar = tqdm(total=num_frames, ncols=60, colour="green")
    vis_images = [None] * num_frames
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(
                runner_draw_handmarks_results,
                loader.get_rgb_image(frame_id),
                [mp_handmarks[serial][:, frame_id] for serial in serials],
                serials,
            ): frame_id
            for frame_id in range(num_frames)
        }
        for future in concurrent.futures.as_completed(futures):
            vis_images[futures[future]] = future.result()
            tqbar.update()
            tqbar.refresh()
        del futures
    tqbar.close()

    tqdm.write("  - Saving vis images...")
    save_vis_folder = save_folder / "vis" / "mp_handmarks"
    save_vis_folder.mkdir(parents=True, exist_ok=True)
    tqbar = tqdm(total=num_frames, ncols=60, colour="green")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(
                write_rgb_image,
                save_vis_folder / f"vis_{frame_id:06d}.png",
                vis_images[frame_id],
            ): frame_id
            for frame_id in range(num_frames)
        }
        for future in concurrent.futures.as_completed(futures):
            future.result()
            tqbar.update()
            tqbar.refresh()
        del futures
    tqbar.close()

    tqdm.write("  - Creating vis video...")
    create_video_from_rgb_images(
        save_folder / "vis" / "mp_handmarks.mp4", vis_images, fps=30
    )

    logger.info(">>>>>>>>>> Hand Detection Completed <<<<<<<<<<")


def args_parser():
    parser = argparse.ArgumentParser(description="Hand Detection")
    parser.add_argument(
        "--sequence_folder",
        type=str,
        required=True,
        help="Path to the sequence folder, python <python_file> --sequence_folder <path_to_sequence_folder>",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = args_parser()
    sequence_folder = Path(args.sequence_folder).resolve()

    main()