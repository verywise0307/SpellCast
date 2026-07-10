from ultralytics import YOLO


def main():
    model = YOLO("yolo26n-pose.pt")

    model.train(
        data="hand-keypoints.yaml",
        epochs=100,
        imgsz=640,
        batch=8,
        workers=2,
        project="runs/hand_pose",
        name="spellcast_hand"
    )


if __name__ == "__main__":
    main()