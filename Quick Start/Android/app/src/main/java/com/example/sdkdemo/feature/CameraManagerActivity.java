package com.example.sdkdemo.feature;

import android.annotation.SuppressLint;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.view.SurfaceView;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.FrameLayout;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.blankj.utilcode.constant.PermissionConstants;
import com.blankj.utilcode.util.PermissionUtils;
import com.example.sdkdemo.R;
import com.example.sdkdemo.base.BasePlayActivity;
import com.example.sdkdemo.databinding.ActivityCameraBinding;
import com.example.sdkdemo.util.CameraVideoProvider;
import com.example.sdkdemo.util.ScreenUtil;
import com.example.sdkdemo.util.SdkUtil;
import com.volcengine.cloudcore.common.mode.CameraId;
import com.volcengine.cloudcore.common.mode.LocalStreamStats;
import com.volcengine.cloudcore.common.mode.LocalVideoStreamDescription;
import com.volcengine.cloudcore.common.mode.LocalVideoStreamError;
import com.volcengine.cloudcore.common.mode.LocalVideoStreamState;
import com.volcengine.cloudcore.common.mode.MirrorMode;
import com.volcengine.cloudcore.common.mode.VideoStreamRequestOption;
import com.volcengine.cloudphone.apiservice.CameraManager;
import com.volcengine.cloudphone.apiservice.outinterface.CameraManagerListener;
import com.volcengine.cloudphone.apiservice.outinterface.RemoteCameraRequestListenerV2;
import com.volcengine.phone.PhonePlayConfig;
import com.volcengine.phone.VePhoneEngine;

import java.text.MessageFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * 该类用于展示与相机{@link CameraManager}相关的功能接口
 * 使用该服务可以实现云端实例对本地视频的采集，采集方式包括内部采集与外部采集。
 * 内部采集使用本地摄像头等设备进行视频采集，不进行加工处理直接发送给云端实例；
 * 外部采集可以对本地采集的视频进行一定的加工处理，再发送给云端实例。
 */
public class CameraManagerActivity extends BasePlayActivity {

    CameraManager mCameraManager;
    private CameraVideoProvider mCameraVideoProvider;
    private ActivityCameraBinding binding;

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ScreenUtil.adaptHolePhone(this);
        binding = ActivityCameraBinding.inflate(getLayoutInflater());
        setContentView(binding.getRoot());
        initView();
        initPlayConfigAndStartPlay();
        mCameraVideoProvider = new CameraVideoProvider(getApplicationContext());
    }

    private void initView() {
        binding.swShowOrHide.setOnCheckedChangeListener((buttonView, isChecked) -> {
            binding.llButtons.setVisibility(isChecked ? View.VISIBLE : View.GONE);
        });

        binding.btnAddLocalCanvas.setOnClickListener(v -> {
            FrameLayout view = findViewById(R.id.fl_local_canvas);
            SurfaceView surfaceView = new SurfaceView(this);
            FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
            params.gravity = Gravity.CENTER;
            surfaceView.setZOrderOnTop(true);
            view.addView(surfaceView, params);
            if (mCameraManager != null) {
                mCameraManager.setLocalVideoCanvas(surfaceView);
            }
            else {
                Log.e(TAG, "mCameraManager == null");
            }
        });

        /*
         * setLocalVideoMirrorMode(MirrorMode mode) -- 设置是否镜像翻转本地摄像头画面
         *
         * @param mode 镜像翻转模式
         *             MIRROR_MODE_OFF(0) -- 不开启镜像翻转
         *             MIRROR_MODE_ON(1) -- 开启镜像翻转
         */
        binding.swEnableMirror.setOnCheckedChangeListener((compoundButton, b) -> {
            if (mCameraManager != null) {
                mCameraManager.setLocalVideoMirrorMode(
                        b ? MirrorMode.MIRROR_MODE_ON : MirrorMode.MIRROR_MODE_OFF);
            }
            else {
                Log.e(TAG, "mCameraManager == null");
            }
        });

        /*
         * setVideoEncoderConfig(List<VideoStreamDescription> videoStreamDescriptions) -- 设置本地视频编码质量策略
         *
         * @param videoStreamDescriptions 视频编码质量参数列表
         *                                参数包括width(宽度), height(高度), frameRate(帧率), maxBitrate(最大码率)
         */
        binding.btnPushMultipleStreams.setOnClickListener(v -> {
            List<LocalVideoStreamDescription> list = new ArrayList<>();
            // 通常只需要推一路流，选择一个最佳的推流参数即可
            list.add(new LocalVideoStreamDescription(1920, 1080, 30, 5000, 5000));
//            list.add(new LocalVideoStreamDescription(1420, 720, 20, 3000, 3000));
//            list.add(new LocalVideoStreamDescription(1000, 500, 20, 2000, 2000));
            if (mCameraManager != null) {
                mCameraManager.setVideoEncoderConfig(list);
            }
            else {
                Log.e(TAG, "mCameraManager == null");
            }
        });

        /*
         * switchCamera(CameraId cameraId) -- 切换前后摄像头
         *
         * @param cameraId 摄像头ID
         *                 FRONT(0) -- 前置
         *                 BACK(1) -- 后置
         * @return 0 -- 调用成功
         *        -1 -- 调用失败
         */
        binding.btnSwitchRearCamera.setOnClickListener(v -> {
            if (mCameraManager != null) {
                mCameraManager.switchCamera(CameraId.BACK);
            }
            else {
                Log.e(TAG, "mCameraManager == null");
            }
        });
        binding.btnSwitchFrontCamera.setOnClickListener(v -> {
            if (mCameraManager != null) {
                mCameraManager.switchCamera(CameraId.FRONT);
            }
            else {
                Log.e(TAG, "mCameraManager == null");
            }
        });
    }

    private void initPlayConfigAndStartPlay() {
        SdkUtil.PlayAuth auth = SdkUtil.getPlayAuth(this);
        SdkUtil.checkPlayAuth(auth,
                p -> {
                    PhonePlayConfig.Builder builder = new PhonePlayConfig.Builder();
                    builder.userId(SdkUtil.getClientUid())
                            .ak(auth.ak)
                            .sk(auth.sk)
                            .token(auth.token)
                            .container(binding.container)
                            .enableLocalKeyboard(true)
                            .roundId(SdkUtil.getRoundId())
                            .podId(auth.podId)
                            .productId(auth.productId)
                            .streamListener(this);
                    VePhoneEngine.getInstance().start(builder.build(), this);
                },
                p -> {
                    showTipDialog(MessageFormat.format(getString(R.string.invalid_phone_play_config) , p));
                });
    }

    @Override
    protected void onResume() {
        super.onResume();
        VePhoneEngine.getInstance().resume();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    @Override
    protected void onPause() {
        super.onPause();
        VePhoneEngine.getInstance().pause();
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (mCameraVideoProvider != null) {
            mCameraVideoProvider.stop();
            mCameraVideoProvider = null;
        }
    }

    @Override
    public void finish() {
        VePhoneEngine.getInstance().stop();
        super.finish();
    }

    @Override
    public void onServiceInit(@NonNull Map<String, Object> extras) {
        super.onServiceInit(extras);
        mCameraManager = VePhoneEngine.getInstance().getCameraManager();
        if (mCameraManager != null) {
            //设置本地摄像头推流状态监听器
            mCameraManager.setCameraManagerListener(new CameraManagerListener() {

                /**
                 * 本地摄像头推流状态改变回调
                 *
                 * @param state 当前推流状态
                 * @param error 推流状态错误码
                 */
                @Override
                public void onLocalVideoStateChanged(LocalVideoStreamState state, LocalVideoStreamError error) {
                    Log.i(TAG, "[onLocalVideoStateChanged] localVideoStreamState: " +
                            state + ", error: " + error);
                }

                /**
                 * 本地首帧被采集回调
                 */
                @Override
                public void onFirstCapture() {
                    Log.i(TAG, "[onFirstCapture]");
                }
            });

            //设置云端请求打开或者关闭本地摄像头的监听器
            mCameraManager.setRemoteRequestListenerV2(new RemoteCameraRequestListenerV2() {
                private VideoStreamRequestOption lastOption;

                /**
                 * 云端请求打开本地摄像头回调
                 *
                 * @param option
                 */
                @Override
                public void onVideoStreamStartRequested(VideoStreamRequestOption option) {
                    Log.d(TAG, "onVideoStreamStartRequested: option:" + option);
                    if (option.width != 0 && option.height != 0) {
                        if (lastOption == null || (lastOption.width != option.width || lastOption.height != option.height)) {
                            lastOption = option;
                            // 根据云端请求的camera分辨率设置采集分辨率
                            // 每种分辨率和帧率对应的码率，可以参考：云手机清晰度档位
                            mCameraManager.setVideoEncoderConfig(Collections.singletonList(
                                    new LocalVideoStreamDescription(option.width, option.height, 30, 5000, 4000)
                            ));
                        }
                    }
                    requestPermissionAndStartSendVideo(option.cameraId);
                }

                /**
                 * 云端请求关闭本地摄像头回调
                 */
                @Override
                public void onVideoStreamStopRequested() {
                    Log.d(TAG, "onVideoStreamStopRequested");
                    mCameraManager.stopVideoStream();
                }
            });
        }
        else {
            Log.e(TAG, "mCameraManager == null");
        }
    }

    @Override
    public void onLocalStreamStats(LocalStreamStats stats) {
        super.onLocalStreamStats(stats);
        // 开启camera采集后，可以通过此回调查看上行视频流统计信息
        Log.d(TAG, "[onLocalStreamStats] stats: " + stats);
    }

    private void requestPermissionAndStartSendVideo(CameraId cameraId) {
        PermissionUtils.permission(PermissionConstants.CAMERA)
                .callback(new PermissionUtils.SimpleCallback() {
                    @SuppressLint("MissingPermission")
                    @Override
                    public void onGranted() {
                        /*
                         * (内部采集使用)
                         * startVideoStream -- 开始指定摄像头采集兵推流，建议在onVideoStreamStartRequested中调用
                         *
                         * @return 0 -- 调用成功
                         *        -1 -- 调用失败
                         */
                        mCameraManager.startVideoStream(cameraId);
                    }

                    @Override
                    public void onDenied() {
                        showToast("无相机权限");
                    }
                }).request();
    }

}
