package com.example.sdkdemo.feature;


import android.annotation.SuppressLint;
import android.os.Bundle;
import android.util.Log;
import android.view.WindowManager;
import android.widget.FrameLayout;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.blankj.utilcode.constant.PermissionConstants;
import com.blankj.utilcode.util.PermissionUtils;
import com.example.sdkdemo.R;
import com.example.sdkdemo.base.BasePlayActivity;
import com.example.sdkdemo.databinding.ActivityAppSimulationBinding;
import com.example.sdkdemo.util.ScreenUtil;
import com.example.sdkdemo.util.SdkUtil;
import com.volcengine.cloudcore.common.mode.CameraId;
import com.volcengine.cloudcore.common.mode.LocalVideoStreamDescription;
import com.volcengine.cloudcore.common.mode.SyncInfoScope;
import com.volcengine.cloudcore.common.mode.SyncInfoStrategy;
import com.volcengine.cloudcore.common.mode.VideoStreamRequestOption;
import com.volcengine.cloudphone.apiservice.CameraManager;
import com.volcengine.cloudphone.apiservice.outinterface.RemoteCameraRequestListenerV2;
import com.volcengine.phone.PhonePlayConfig;
import com.volcengine.phone.VePhoneEngine;

import java.text.MessageFormat;
import java.util.Collections;
import java.util.Map;

/**
 * @desc: 应用仿真问题最佳实践
 * 核心要点：
 * - 1. 开启定位同步
 * - 2. 开启光线传感器
 * - 3. 开启wifi、radio信号同步
 * @date: 2026/01/12
 */
public class AppSimulationActivity extends BasePlayActivity {

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ScreenUtil.adaptHolePhone(this);
        ActivityAppSimulationBinding binding = ActivityAppSimulationBinding.inflate(getLayoutInflater());
        setContentView(binding.getRoot());
        initPlayConfigAndStartPlay(binding.container);
        PermissionUtils.permission(PermissionConstants.CAMERA, PermissionConstants.LOCATION).request();
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
    }

    @Override
    public void finish() {
        VePhoneEngine.getInstance().stop();
        super.finish();
    }

    @Override
    public void onServiceInit(@NonNull Map<String, Object> extras) {
        super.onServiceInit(extras);
        CameraManager cameraManager = VePhoneEngine.getInstance().getCameraManager();
        if (cameraManager != null) {
            cameraManager.setRemoteRequestListenerV2(new RemoteCameraRequestListenerV2() {
                private VideoStreamRequestOption lastOption;
                @Override
                public void onVideoStreamStartRequested(VideoStreamRequestOption option) {
                    Log.d(TAG, "onVideoStreamStartRequested: option:" + option);
                    if (option.width != 0 && option.height != 0) {
                        if (lastOption == null || (lastOption.width != option.width || lastOption.height != option.height)) {
                            lastOption = option;
                            // 根据请求的相机分辨率调整采集的分辨率
                            cameraManager.setVideoEncoderConfig(Collections.singletonList(
                                    new LocalVideoStreamDescription(option.width, option.height, 30, 5000, 4000)
                            ));
                        }
                    }
                    requestPermissionAndStartSendVideo(option.cameraId);
                }

                @Override
                public void onVideoStreamStopRequested() {
                    Log.d(TAG, "onVideoStreamStopRequested");
                    cameraManager.stopVideoStream();
                }
            });
        }
    }

    private void initPlayConfigAndStartPlay(FrameLayout container) {
        SdkUtil.PlayAuth auth = SdkUtil.getPlayAuth(this);
        SdkUtil.checkPlayAuth(auth,
                p -> {
                    PhonePlayConfig.Builder builder = new PhonePlayConfig.Builder();
                    builder.userId(SdkUtil.getClientUid())
                            .ak(auth.ak)
                            .sk(auth.sk)
                            .token(auth.token)
                            .productId(auth.productId)
                            .podId(auth.podId)
                            .container(container)
                            .enableLocationService(true)
                            .enableLightSensor(true)  // setLightSensorState作用相同
                            .syncInfoScope(SyncInfoScope.ALL)
                            .syncInfoStrategy(SyncInfoStrategy.whenChanged())
                            .remoteWindowSize(0,0)  //按pod原始分辨率推流
                            .streamListener(this);
                    VePhoneEngine.getInstance().start(builder.build(), this);
                },
                p -> {
                    showTipDialog(MessageFormat.format(getString(R.string.invalid_phone_play_config) , p));
                });
    }

    private void requestPermissionAndStartSendVideo(CameraId cameraId) {
        PermissionUtils.permission(PermissionConstants.CAMERA)
                .callback(new PermissionUtils.SimpleCallback() {
                    @SuppressLint("MissingPermission")
                    @Override
                    public void onGranted() {
                        VePhoneEngine.getInstance().getCameraManager().startVideoStream(cameraId);
                    }

                    @Override
                    public void onDenied() {
                        showToast("无相机权限");
                    }
                }).request();
    }
}
